
import hashlib
import re
from typing import Any

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


class RAGRetriever:
    def __init__(
        self,
        chunks: list[dict[str, Any]],
        dimensions: int = 384,
        embedding_client: Any | None = None,
    ) -> None:
        self.chunks = chunks
        self.dimensions = dimensions
        self.embedding_client = embedding_client
        self._api_vectors_ready = False
        self.vectors = np.array([self._embed(self._chunk_text(chunk)) for chunk in chunks], dtype="float32")
        self.index = None
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self.index = None
        if faiss is not None and len(self.vectors):
            self.index = faiss.IndexFlatIP(self.dimensions)
            self.index.add(self.vectors)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not self.chunks:
            return []
        query_vec = self._embed(query).reshape(1, -1).astype("float32")
        scores = self.vectors @ query_vec[0]
        boosted_scores = [
            float(score) + self._keyword_boost(query, self.chunks[index])
            for index, score in enumerate(scores)
        ]
        order = np.argsort(boosted_scores)[::-1][:top_k]
        return [
            {**self.chunks[index], "score": round(float(boosted_scores[index]), 4)}
            for index in order
            if index >= 0
        ]

    async def retrieve_async(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Retrieve chunks using API embeddings when configured, with hash fallback."""
        if not self.chunks:
            return []
        if self.embedding_client is None:
            return self.retrieve(query, top_k)

        await self._ensure_api_vectors()
        query_vec = await self.embedding_client.embed([query])
        query_vec = self._normalize_vectors(query_vec.astype("float32"))
        scores = self.vectors @ query_vec[0]
        boosted_scores = [
            float(score) + self._keyword_boost(query, self.chunks[index])
            for index, score in enumerate(scores)
        ]
        order = np.argsort(boosted_scores)[::-1][:top_k]
        return [
            {**self.chunks[index], "score": round(float(boosted_scores[index]), 4)}
            for index in order
            if index >= 0
        ]

    async def _ensure_api_vectors(self) -> None:
        if self._api_vectors_ready or self.embedding_client is None:
            return
        texts = [self._chunk_text(chunk) for chunk in self.chunks]
        vectors = await self.embedding_client.embed(texts)
        self.vectors = self._normalize_vectors(vectors.astype("float32"))
        self.dimensions = int(self.vectors.shape[1]) if len(self.vectors.shape) == 2 else self.dimensions
        self._rebuild_index()
        self._api_vectors_ready = True

    @staticmethod
    def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms

    def _embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, dtype="float32")
        tokens = self._tokens(text)
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

    @classmethod
    def _tokens(cls, text: str) -> list[str]:
        tokens = TOKEN_RE.findall(text.lower())
        expanded = list(tokens)
        for match in CJK_RE.findall(text):
            if len(match) <= 1:
                continue
            for size in (2, 3, 4):
                expanded.extend(match[index : index + size] for index in range(len(match) - size + 1))
        return expanded

    @classmethod
    def _keyword_boost(cls, query: str, chunk: dict[str, Any]) -> float:
        normalized_query = query.lower()
        title = str(chunk.get("title", "")).lower()
        content = str(chunk.get("content", "")).lower()
        keywords = [str(keyword).lower() for keyword in chunk.get("keywords", [])]

        boost = 0.0
        if title and title in normalized_query:
            boost += 1.2
        for keyword in keywords:
            if keyword and keyword in normalized_query:
                boost += 0.8
        query_terms = set(cls._tokens(normalized_query))
        if title and title in query_terms:
            boost += 0.5
        boost += 0.18 * sum(1 for keyword in keywords if keyword in query_terms)
        boost += 0.05 * sum(1 for term in query_terms if len(term) >= 2 and term in content)
        boost += 0.04 * int(chunk.get("importance", 3))
        return boost
