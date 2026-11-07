"""Spanish lexical evidence scoring used as the retrieval precision gate.

Ported from the former keyword-only RAG: accent-insensitive normalization,
light plural stemming, a small domain synonym map and 4+ character prefix
matching for conjugations. Vector search supplies recall; this module only
answers "does the question actually share content words with the chunk?".
"""
from __future__ import annotations

import unicodedata

# Common Spanish function words that add noise to overlap scoring.
SPANISH_STOPWORDS: set[str] = {
    "que", "para", "con", "los", "las", "del", "una", "uno", "por",
    "como", "esta", "este", "esto", "son", "hay", "tiene", "tengo",
    "hacen", "hace", "sus", "mis", "tus", "les", "ese", "esa",
}

# Generic question words are excluded on purpose. Every FAQ heading starts
# with "¿Cuál/Cuándo/Dónde/Puedo...?", so keeping them let off-domain
# questions ("¿cuál es la capital de Francia?") collect lexical evidence
# from an unrelated section heading. The measured gate depends on this.
INTERROGATIVES: set[str] = {
    "cual", "cuales", "cuando", "donde", "adonde", "quien", "quienes",
    "cuanto", "cuanta", "cuantos", "cuantas", "puedo", "puede", "podria",
}
SPANISH_STOPWORDS |= INTERROGATIVES

# Backwards compatibility alias
STOPWORDS = SPANISH_STOPWORDS

# Domain synonyms for the tiny FAQ vocabulary. Keys and values are in the
# normalized + stemmed forms produced below (no accents, lowercase, plural
# already stripped: "pais" stays "pais", "horas" -> "hora").
_STEM_EQUIVALENTS: dict[str, set[str]] = {
    "interior": {"pais"},
    "pais": {"interior"},
    "envio": {"enviamo", "enviar"},
    "enviamo": {"envio"},
    "tarda": {"hora", "demora"},
    "tardan": {"hora"},
    "demora": {"tarda", "hora"},
    "hora": {"tarda", "demora"},
    "necesito": {"necesita", "requisito"},
    "pedir": {"solicitar"},
    "solicitar": {"pedir"},
    "queda": {"ubicado", "direccion"},
    "ubicado": {"queda", "direccion"},
    "direccion": {"queda", "ubicado"},
    "domicilio": {"envio", "enviamo"},
    # "cuanto" is a stopword (every FAQ question starts with it), so only the
    # content-word side of the pair is kept.
    "costo": {"precio"},
    "precio": {"costo"},
    # Added with the vector RAG: payment, human support, refunds, shipping.
    "pagar": {"pago"},
    "pago": {"pagar"},
    "cuota": {"pago"},
    "humano": {"soporte"},
    "hablar": {"contacto"},
    "plata": {"reembolso"},
    "reembolso": {"plata"},
    "grati": {"costo"},  # stem of "gratis"
    "extranjero": {"pais"},
}

# Backwards compatibility alias
SYNONYMS = _STEM_EQUIVALENTS


def normalize(text: str) -> str:
    """Strip accents and lowercase ASCII-folded text."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore")
    return folded.decode("ascii").lower()


_normalize = normalize


def stem(token: str) -> str:
    """Light plural stemming for Spanish words.

    Examples:
        - "devoluciones" -> "devolucion"
        - "horas" -> "hora"
        - "enviamos" -> "enviamo"
    """
    if len(token) > 5 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


_stem = stem


def tokenize(text: str) -> set[str]:
    """Extract normalized alphanumeric stems without stopwords or tiny words."""
    return {
        stem(token)
        for token in "".join(
            ch if ch.isalnum() else " " for ch in normalize(text)
        ).split()
        if len(token) > 2 and token not in SPANISH_STOPWORDS
    }


_tokenize = tokenize


def common_prefix_len(a: str, b: str) -> int:
    """Count length of shared initial characters between two strings."""
    count = 0
    for x, y in zip(a, b):
        if x != y:
            break
        count += 1
    return count


_common_prefix_len = common_prefix_len


def variant_best(variant: str, doc: set[str]) -> float:
    """Match score for a token/variant against doc stems: 1.0 exact, 0.7 prefix."""
    if variant in doc:
        return 1.0
    if len(variant) < 4:
        return 0.0
    for candidate in doc:
        if len(candidate) >= 4 and common_prefix_len(variant, candidate) >= 4:
            return 0.7
    return 0.0


_variant_best = variant_best


def score(query: set[str], doc: set[str]) -> float:
    """Score query stems against doc stems using stem equivalents.

    One value per query concept: the best across its synonym variants.
    Best match wins per concept so long documents do not inflate the score.
    """
    total = 0.0
    for token in query:
        variants = {token} | _STEM_EQUIVALENTS.get(token, set())
        total += max(variant_best(variant, doc) for variant in variants)
    return total


_score = score


def lexical_evidence(question: str, text: str) -> float:
    """Return how much content the question shares with ``text``.

    Zero means no lexical evidence at all, which lets the retrieval gate
    reject a semantically close but unrelated chunk.
    """
    query = tokenize(question)
    if not query:
        return 0.0
    return score(query, tokenize(text))


__all__ = [
    "INTERROGATIVES",
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
