"""Static embeddings with model2vec (§7.6). Vectors are float32 and L2-normalized."""

from typing import Protocol

import numpy as np
import numpy.typing as npt

from moira.logging import get_logger

log = get_logger(__name__)

Vector = npt.NDArray[np.float32]


class Embedder(Protocol):
    dim: int

    def encode(self, texts: list[str]) -> npt.NDArray[np.float32]:
        """One L2-normalized float32 row per text."""
        ...


def normalize(m: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


class Model2VecEmbedder:
    """Loads once at startup. ``dimensionality=256`` and int8 verified locally (J14)."""

    def __init__(self, model_id: str, dim: int, quantize: str) -> None:
        from model2vec import StaticModel

        self.model = StaticModel.from_pretrained(model_id, quantize_to=quantize, dimensionality=dim)
        self.dim = int(self.model.dim)
        log.info("embed_loaded", model=model_id, dim=self.dim)

    def encode(self, texts: list[str]) -> npt.NDArray[np.float32]:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return normalize(np.asarray(self.model.encode(texts), dtype=np.float32))


class HashEmbedder:
    """Deterministic, dependency-free embedder for tests and offline dev.

    Hashes word and character-trigram features into ``dim`` buckets, so texts that share
    words land near each other. Not used in production.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        words = [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]
        feats = [f"w:{w}" for w in words]
        for w in words:
            padded = f"#{w}#"
            feats += [f"t:{padded[i : i + 3]}" for i in range(len(padded) - 2)]
        return feats

    def encode(self, texts: list[str]) -> npt.NDArray[np.float32]:
        import zlib

        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for f in self._features(text):
                h = zlib.crc32(f.encode())
                out[row, h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
                if f.startswith("w:"):
                    out[row, (h >> 8) % self.dim] += 1.0
        return normalize(out)


def load_embedder(model_id: str, dim: int, quantize: str, *, fake: bool) -> Embedder | None:
    """The real model, a hash embedder for tests, or None when loading fails (degraded mode)."""
    if fake:
        return HashEmbedder(dim)
    try:
        return Model2VecEmbedder(model_id, dim, quantize)
    except Exception as exc:  # noqa: BLE001  # §8.8: search keeps working without vectors
        log.error("embed_failed", error=type(exc).__name__)
        return None
