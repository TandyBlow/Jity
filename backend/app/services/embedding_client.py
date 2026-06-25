"""Embedding client using DeepSeek embedding API (HARD-02).

Auto-detects embedding dimension via test call.
Falls back to SHA-256 hash if API is unavailable.
"""

import hashlib
import logging

import numpy as np
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Fallback dimension used when API is not available
HASH_EMBEDDING_DIM = 256

# Candidate model names to try in order
CANDIDATE_MODELS = ["deepseek-embed", "deepseek-chat"]


class EmbeddingClient:
    """Produces text embeddings via DeepSeek API with hash fallback.

    Uses the openai SDK (already a dependency) pointed at DeepSeek's
    base URL. Auto-detects the embedding dimension on first call.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        fallback_dim: int = HASH_EMBEDDING_DIM,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
        self._dim: int | None = None
        self._model: str | None = None
        self._fallback_dim = fallback_dim
        self._api_available: bool | None = None  # None = not checked yet

    @property
    def dimension(self) -> int:
        """Return detected embedding dimension (lazy init)."""
        if self._dim is None:
            self._dim = self._fallback_dim
        return self._dim

    @property
    def model(self) -> str:
        return self._model or "sha256-hash"

    async def _detect_dimension(self) -> tuple[str, int] | None:
        """Try candidate models to detect which one works and its dimension."""
        for model_name in CANDIDATE_MODELS:
            try:
                response = await self._client.embeddings.create(
                    model=model_name,
                    input="test",
                )
                if response.data and len(response.data) > 0:
                    dim = len(response.data[0].embedding)
                    logger.info(
                        "Embedding API: model=%s dimension=%d", model_name, dim
                    )
                    return model_name, dim
            except Exception:
                logger.debug("Embedding model %s unavailable, trying next", model_name)
                continue
        return None

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for a list of texts.

        Returns:
            numpy array of shape (len(texts), dimension)
        """
        if self._api_available is None:
            result = await self._detect_dimension()
            if result:
                self._model, self._dim = result
                self._api_available = True
            else:
                self._api_available = False
                logger.warning(
                    "Embedding API unavailable — falling back to SHA-256 hash"
                )

        if self._api_available and self._model:
            try:
                response = await self._client.embeddings.create(
                    model=self._model,
                    input=texts,
                )
                return np.array(
                    [d.embedding for d in response.data], dtype=np.float32
                )
            except Exception as exc:
                logger.warning("Embedding API call failed: %s", exc)
                self._api_available = False

        # Fallback: SHA-256 hash embeddings
        return self._hash_embed(texts)

    def _hash_embed(self, texts: list[str]) -> np.ndarray:
        """Generate SHA-256 hash-based embeddings (original approach).

        Each text gets a 256-dim unit vector derived from its SHA-256 hash.
        """
        vectors = np.zeros((len(texts), self._fallback_dim), dtype=np.float32)
        for i, text in enumerate(texts):
            hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
            # Use first 256 bits = 32 bytes; repeat to fill 256 dims if needed
            bits = np.unpackbits(np.frombuffer(hash_bytes[:32], dtype=np.uint8))
            # Normalize to unit vector
            vec = bits.astype(np.float32) * 2.0 - 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors[i] = vec
        return vectors
