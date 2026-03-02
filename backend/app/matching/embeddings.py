import os
import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

try:
    import openai
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False


OPENAI_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _fallback_embedding(text: str, dim: int = 256) -> List[float]:
    """Deterministic fallback embedding using byte frequency modulo `dim`.

    Not semantic but stable when OpenAI is unavailable.
    """
    b = text.encode("utf-8", errors="ignore")
    counts = [0] * dim
    for byte in b:
        counts[byte % dim] += 1
    arr = np.array(counts, dtype=float)
    if arr.sum() > 0:
        arr = arr / np.linalg.norm(arr)
    return arr.tolist()


def embed_text(text: str) -> List[float]:
    """Return embedding vector for `text`.

    Tries OpenAI (if available and configured), otherwise returns a fallback vector.
    """
    if _HAS_OPENAI and os.getenv("OPENAI_API_KEY"):
        try:
            client = openai.OpenAI()
            resp = client.embeddings.create(model=OPENAI_MODEL, input=text)
            vec = resp.data[0].embedding
            # normalize
            arr = np.array(vec, dtype=float)
            norm = np.linalg.norm(arr)
            if norm > 0:
                arr = arr / norm
            return arr.tolist()
        except Exception as e:
            logger.warning("OpenAI embedding failed, using fallback: %s", e)
            return _fallback_embedding(text)
    return _fallback_embedding(text)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    a_arr = np.array(a, dtype=float)
    b_arr = np.array(b, dtype=float)
    if a_arr.size == 0 or b_arr.size == 0:
        return 0.0
    # if dimensions differ, pad the smaller with zeros
    if a_arr.shape != b_arr.shape:
        maxd = max(a_arr.size, b_arr.size)
        a2 = np.zeros(maxd, dtype=float)
        b2 = np.zeros(maxd, dtype=float)
        a2[: a_arr.size] = a_arr
        b2[: b_arr.size] = b_arr
        a_arr = a2
        b_arr = b2
    na = np.linalg.norm(a_arr)
    nb = np.linalg.norm(b_arr)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (na * nb))
