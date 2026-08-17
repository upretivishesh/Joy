import time
from functools import lru_cache

import numpy as np
from openai import OpenAI, RateLimitError, APIError


EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


# ---------------------------------------------------------------------------
# Reuse one OpenAI client per API key instead of constructing a new one on
# every call. The old code did `OpenAI(api_key=api_key)` inside
# get_embedding(), meaning a 50-resume batch created 50 separate client
# instances for no benefit — client construction is cheap but not free,
# and it's simply unnecessary repeated work.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=8)
def _get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def _embedding_dim(model: str) -> int:
    return EMBEDDING_DIMENSIONS.get(model, 1536)


def get_embedding(
    text: str, api_key: str, model: str = "text-embedding-3-small", retries: int = 2
) -> np.ndarray:
    """Get embedding vector for a single text, with basic retry on rate limits."""
    dim = _embedding_dim(model)
    if not text or not api_key:
        return np.zeros(dim)

    client = _get_client(api_key)
    text = text.replace("\n", " ")[:8000]

    for attempt in range(retries + 1):
        try:
            response = client.embeddings.create(input=[text], model=model)
            return np.array(response.data[0].embedding)
        except RateLimitError:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return np.zeros(dim)
        except APIError:
            return np.zeros(dim)
        except Exception:
            return np.zeros(dim)

    return np.zeros(dim)


def get_embeddings_batch(
    texts: list[str], api_key: str, model: str = "text-embedding-3-small", retries: int = 2
) -> list[np.ndarray]:
    """
    Embed MULTIPLE texts in as few API calls as possible.

    This is the fix for the biggest hidden cost in the old code: screening
    a batch of N resumes against one JD made N+1 sequential single-item
    calls (one per resume, plus one for the JD, repeated every time since
    nothing was cached). OpenAI's embeddings endpoint accepts a list of
    inputs and returns all vectors in one response — a 50-resume batch
    becomes 1 call instead of 50, both cheaper and dramatically faster.

    Falls back to zero vectors (matching the single-call behavior) for any
    text that's empty, and preserves input order in the returned list.
    """
    dim = _embedding_dim(model)
    if not api_key or not texts:
        return [np.zeros(dim) for _ in texts]

    # Track which indices actually have text to embed; skip empties.
    non_empty_indices = [i for i, t in enumerate(texts) if t and t.strip()]
    if not non_empty_indices:
        return [np.zeros(dim) for _ in texts]

    clean_texts = [texts[i].replace("\n", " ")[:8000] for i in non_empty_indices]
    client = _get_client(api_key)

    results = [np.zeros(dim) for _ in texts]

    # OpenAI embeddings API accepts up to 2048 inputs per call in practice;
    # chunk defensively at 100 to stay well under any payload/token limits
    # for long resume texts.
    CHUNK_SIZE = 100
    for chunk_start in range(0, len(clean_texts), CHUNK_SIZE):
        chunk = clean_texts[chunk_start : chunk_start + CHUNK_SIZE]
        chunk_indices = non_empty_indices[chunk_start : chunk_start + CHUNK_SIZE]

        for attempt in range(retries + 1):
            try:
                response = client.embeddings.create(input=chunk, model=model)
                for offset, item in enumerate(response.data):
                    results[chunk_indices[offset]] = np.array(item.embedding)
                break
            except RateLimitError:
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                # leave zeros for this chunk on final failure
            except Exception:
                break

    return results


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    if np.all(vec1 == 0) or np.all(vec2 == 0):
        return 0.0
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))


def semantic_similarity_score(
    resume_text: str,
    jd_text: str,
    api_key: str,
    model: str = "text-embedding-3-small",
) -> float:
    """Single-pair semantic match score (0-100). Kept for backward
    compatibility with existing call sites that score one resume at a time."""
    if not api_key or not resume_text or not jd_text:
        return 50.0
    try:
        resume_emb = get_embedding(resume_text, api_key, model)
        jd_emb = get_embedding(jd_text, api_key, model)
        similarity = cosine_similarity(resume_emb, jd_emb)
        score = max(0, min(100, (similarity - 0.55) * 250))
        return round(score, 1)
    except Exception as e:
        print(f"Semantic scoring error: {e}")
        return 50.0


def semantic_similarity_scores_batch(
    resume_texts: list[str],
    jd_text: str,
    api_key: str,
    model: str = "text-embedding-3-small",
) -> list[float]:
    """
    Batch version: score MANY resumes against ONE job description in a
    small, fixed number of API calls instead of one call pair per resume.

    This is the function screening.py's batch loop should call once per
    screening run (embed the JD once, embed all resumes in one/few calls),
    rather than calling semantic_similarity_score() once per resume, which
    was silently re-embedding the identical JD text on every single
    candidate in the batch.
    """
    if not api_key or not jd_text or not resume_texts:
        return [50.0] * len(resume_texts)

    try:
        jd_emb = get_embedding(jd_text, api_key, model)
        resume_embs = get_embeddings_batch(resume_texts, api_key, model)

        scores = []
        for emb in resume_embs:
            similarity = cosine_similarity(emb, jd_emb)
            score = max(0, min(100, (similarity - 0.55) * 250))
            scores.append(round(score, 1))
        return scores
    except Exception as e:
        print(f"Batch semantic scoring error: {e}")
        return [50.0] * len(resume_texts)
