"""Infrastructure package for external clients, storage, and text processing."""

from app.infrastructure.lexical import (
    INTERROGATIVES,
    SPANISH_STOPWORDS,
    STOPWORDS,
    SYNONYMS,
    _STEM_EQUIVALENTS,
    common_prefix_len,
    lexical_evidence,
    normalize,
    score,
    stem,
    tokenize,
    variant_best,
)
from app.infrastructure.ollama import (
    DOCUMENT_PREFIX,
    QUERY_PREFIX,
    OllamaChatClient,
    OllamaEmbedder,
)

__all__ = [
    "DOCUMENT_PREFIX",
    "INTERROGATIVES",
    "QUERY_PREFIX",
    "OllamaChatClient",
    "OllamaEmbedder",
    "SPANISH_STOPWORDS",
    "STOPWORDS",
    "SYNONYMS",
    "_STEM_EQUIVALENTS",
    "common_prefix_len",
    "lexical_evidence",
    "normalize",
    "score",
    "stem",
    "tokenize",
    "variant_best",
]
