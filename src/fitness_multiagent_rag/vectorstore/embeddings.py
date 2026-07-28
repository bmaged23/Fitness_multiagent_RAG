from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from sentence_transformers import SentenceTransformer
from config.settings import EMBEDDING_MODEL

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
    return _model


def embed_one(text: str) -> list[float]:
    vecs = _get_model().encode(
        [text], normalize_embeddings=True, show_progress_bar=False
    )
    return vecs[0].tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    vecs = _get_model().encode(
        texts, normalize_embeddings=True, show_progress_bar=False
    )
    return [v.tolist() for v in vecs]
