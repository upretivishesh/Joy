import time
from functools import lru_cache

import numpy as np
from openai import OpenAI, RateLimitError, APIError


EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

# text-embedding-3-small clusters real resume/JD pairs around 0.55–0.85.
# 0.40 -> 0, 0.65 -> 50, 0.90 -> 100. The old (sim - 0.55) * 250 map
# turned that band into a cliff: 0.55 became 0 and 0.90 became ~88.
SEMANTIC_FLOOR = 0.40
SEMANTIC_SPAN = 200.0
NEUTRAL_SCORE = 55.0


@lru_cache(maxsize=8)
def _get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def _embedding_dim(model: str) -> int:
    return EMBEDDING_DIMENSIONS.get(model, 1536)


def semantic_from_cosine(similarity: float) -> float:
    score = (float(similarity) - SEMANTIC_FLOOR) * SEMANTIC_SPAN
    return round(max(0.0, min(100.0, score)), 1)


def _pair_score(resume_emb: np.ndarray, jd_emb: np.ndarray) -> float:
    """Zero vector means the embedding failed. That is neutral, not unrelated."""
    if resume_emb is None or jd_emb is None:
        return NEUTRAL_SCORE
    if np.all(resume_emb == 0) or np.all(jd_emb == 0):
        return NEUTRAL_SCORE
    similarity = cosine_similarity(resume_emb, jd_emb)
    if similarity <= 0:
        return NEUTRAL_SCORE
    return semantic_from_cosine(similarity)


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

    Falls back to zero vectors for any text that is empty or whose request
    fails, and preserves input order in the returned list.
    """
    dim = _embedding_dim(model)
    if not api_key or not texts:
        return [np.zeros(dim) for _ in texts]

    non_empty_indices = [i for i, t in enumerate(texts) if t and t.strip()]
    if not non_empty_indices:
        return [np.zeros(dim) for _ in texts]

    clean_texts = [texts[i].replace("\n", " ")[:8000] for i in non_empty_indices]
    client = _get_client(api_key)

    results = [np.zeros(dim) for _ in texts]

    CHUNK_SIZE = 100
    for chunk_start in range(0, len(clean_texts), CHUNK_SIZE):
        chunk = clean_texts[chunk_start : chunk_start + CHUNK_SIZE]
        chunk_indices = non_empty_indices[chunk_start : chunk_start + CHUNK_SIZE]

        for attempt in range(retries + 1):
            try:
                response = client.embeddings.create(input=chunk, model=model)
                # item.index is the position inside this request. Do not trust
                # response order; a shuffled batch would score the wrong resume.
                for item in response.data:
                    results[chunk_indices[item.index]] = np.array(item.embedding)
                break
            except RateLimitError:
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
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
    """Single-pair semantic match score (0-100)."""
    if not api_key or not resume_text or not jd_text:
        return NEUTRAL_SCORE
    try:
        resume_emb = get_embedding(resume_text, api_key, model)
        jd_emb = get_embedding(jd_text, api_key, model)
        return _pair_score(resume_emb, jd_emb)
    except Exception as e:
        print(f"Semantic scoring error: {e}")
        return NEUTRAL_SCORE


def semantic_similarity_scores_batch(
    resume_texts: list[str],
    jd_text: str,
    api_key: str,
    model: str = "text-embedding-3-small",
) -> list[float]:
    """
    Score many resumes against one JD.

    One failed resume becomes 55, not 0, so a rate-limit zero vector cannot
    knock a real candidate out of the ranking.
    """
    if not api_key or not jd_text or not resume_texts:
        return [NEUTRAL_SCORE] * len(resume_texts)

    try:
        jd_emb = get_embedding(jd_text, api_key, model)
        resume_embs = get_embeddings_batch(resume_texts, api_key, model)
        return [_pair_score(emb, jd_emb) for emb in resume_embs]
    except Exception as e:
        print(f"Batch semantic scoring error: {e}")
        return [NEUTRAL_SCORE] * len(resume_texts)
