"""Local text embedding helpers."""

from functools import lru_cache


EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
QUESTION_PREFIXES = (
    "can you explain ",
    "could you explain ",
    "please explain ",
    "explain ",
    "what is ",
    "what are ",
    "tell me about ",
)


@lru_cache(maxsize=1)
def _get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def _normalize_text(text: str) -> str:
    normalized_text = " ".join(text.strip().lower().split()).rstrip("?.!")
    for prefix in QUESTION_PREFIXES:
        if normalized_text.startswith(prefix):
            return normalized_text.removeprefix(prefix).strip()
    return normalized_text


def get_embedding(text: str) -> list[float]:
    """Return an embedding for normalized text as a plain Python list."""
    normalized_text = _normalize_text(text)
    embedding = _get_embedding_model().encode(normalized_text, normalize_embeddings=True)
    return embedding.tolist()


def preload_embedding_model() -> None:
    """Load and cache the embedding model for process startup."""
    _get_embedding_model()
