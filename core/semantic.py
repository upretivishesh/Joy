import numpy as np
from openai import OpenAI

def get_embedding(text: str, api_key: str, model: str = "text-embedding-3-small") -> np.ndarray:
    """Get embedding vector for text using OpenAI."""
    if not text or not api_key:
        return np.zeros(1536)  # text-embedding-3-small dimension
    
    client = OpenAI(api_key=api_key)
    text = text.replace("\n", " ")[:8000]  # truncate for safety
    
    response = client.embeddings.create(
        input=[text],
        model=model
    )
    return np.array(response.data[0].embedding)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    if np.all(vec1 == 0) or np.all(vec2 == 0):
        return 0.0
    return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))


def semantic_similarity_score(
    resume_text: str, 
    jd_text: str, 
    api_key: str,
    model: str = "text-embedding-3-small"
) -> float:
    """
    Semantic match score (0-100) using embeddings.
    Captures synonyms, context, and related skills.
    """
    if not api_key or not resume_text or not jd_text:
        return 50.0

    try:
        resume_emb = get_embedding(resume_text, api_key, model)
        jd_emb = get_embedding(jd_text, api_key, model)
        similarity = cosine_similarity(resume_emb, jd_emb)
        
        # Scale to 0-100 (most real matches fall between 0.65–0.92)
        score = max(0, min(100, (similarity - 0.55) * 250))
        return round(score, 1)
    except Exception as e:
        print(f"Semantic scoring error: {e}")
        return 50.0
