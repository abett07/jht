"""Embedding cache: avoid re-embedding identical text by hashing."""
import hashlib
import json
from typing import List, Optional

# In-memory cache; swap to Redis or DB for persistence across restarts.
_cache: dict = {}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def get_cached(text: str) -> Optional[List[float]]:
    return _cache.get(_text_hash(text))


def set_cached(text: str, embedding: List[float]) -> None:
    _cache[_text_hash(text)] = embedding


def cached_embed(text: str, embed_fn) -> List[float]:
    """Return cached embedding or compute via `embed_fn`, cache, and return."""
    h = _text_hash(text)
    if h in _cache:
        return _cache[h]
    vec = embed_fn(text)
    _cache[h] = vec
    return vec
