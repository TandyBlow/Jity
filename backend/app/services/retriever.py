from __future__ import annotations

import hashlib
import re
from typing import Any

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


class RAGRetriever:
    def __init__(self, chunks: list[dict[str, Any]], dimensions: int = 384) -> None:
        self.chunks = chunks
        self.dimensions = dimensions
        self.vectors = np.array([self._embed(self._chunk_text(chunk)) for chunk in chunks], dtype="float32")
        self.index = None
        if faiss is not None and len(self.vectors):
            self.index = faiss.IndexFlatIP(dimensions)
            self.index.add(self.vectors)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not self.chunks:
            return []
        query_vec = self._embed(query).reshape(1, -1).astype("float32")
        if self.index is not None:
            scores, indices = self.index.search(query_vec, min(top_k, len(self.chunks)))
            pairs = zip(indices[0].tolist(), scores[0].tolist())
        else:
            scores = self.vectors @ query_vec[0]
            order = np.argsort(scores)[::-1][:top_k]
            pairs = ((int(index), float(scores[index])) for index in order)
        return [
            {**self.chunks[index], "score": round(float(score), 4)}
            for index, score in pairs
            if index >= 0
        ]

    def _embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, dtype="float32")
        tokens = TOKEN_RE.findall(text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            weight = 1.0 + min(len(token), 8) / 10.0
            vector[bucket] += weight
        norm = np.linalg.norm(vector)
        if norm:
            vector /= norm
        return vector

    @staticmethod
    def _chunk_text(chunk: dict[str, Any]) -> str:
        keywords = " ".join(chunk.get("keywords", []))
        return f"{chunk.get('title', '')} {keywords} {chunk.get('content', '')}"
