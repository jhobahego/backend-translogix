"""Unit tests for the Spanish lexical analyzer and retrieval precision gate.

Covers:
- normalize: accent stripping, lowercase folding
- stem: Spanish plural trimming
- tokenize: punctuation removal, stopword filtering, length filtering
- SPANISH_STOPWORDS: interrogative exclusion
- lexical_evidence: matching, non-matching, synonyms, empty queries
"""
from __future__ import annotations

import pytest

from app.infrastructure.lexical import (
    INTERROGATIVES,
    SPANISH_STOPWORDS,
    _STEM_EQUIVALENTS,
    common_prefix_len,
    lexical_evidence,
    normalize,
    stem,
    tokenize,
    variant_best,
)


def test_normalize_accents_and_case() -> None:
    """Normalize strips accents and lowercases ASCII-folded characters."""
    assert normalize("BOGOTÁ") == "bogota"
    assert normalize("Canción") == "cancion"
    assert normalize("Envíos aéreos") == "envios aereos"
    assert normalize("Ñandú") == "nandu"
    assert normalize("¿Cuál es el término?") == "cual es el termino?"


def test_stem_rules() -> None:
    """Stem trims Spanish plurals while preserving short word roots."""
    # Words with length > 5 ending with 'es'
    assert stem("devoluciones") == "devolucion"
    assert stem("camiones") == "camion"

    # Words with length > 4 ending with 's'
    assert stem("horas") == "hora"
    assert stem("enviamos") == "enviamo"
    assert stem("tarifas") == "tarifa"

    # Short words preserved
    assert stem("mes") == "mes"
    assert stem("sol") == "sol"
    assert stem("tres") == "tres"
    assert stem("pais") == "pais"


def test_tokenize_filters_stopwords_and_short_words() -> None:
    """Tokenize extracts stems, discards stopwords and tokens <= 2 chars."""
    text = "¿Cuál es el costo del envío para Bogotá?"
    tokens = tokenize(text)

    # "cual", "es", "el", "del", "para" are stopwords or short words
    assert "cual" not in tokens
    assert "el" not in tokens
    assert "del" not in tokens
    assert "para" not in tokens

    # Content stems must remain
    assert "costo" in tokens
    assert "envio" in tokens
    assert "bogota" in tokens


def test_spanish_stopwords_and_interrogatives() -> None:
    """Interrogatives are explicitly part of SPANISH_STOPWORDS to prevent off-domain false matches."""
    for word in ("cual", "cuando", "donde", "cuanto", "quien", "puedo"):
        assert word in INTERROGATIVES
        assert word in SPANISH_STOPWORDS

    for stopword in ("que", "para", "con", "los", "las", "del"):
        assert stopword in SPANISH_STOPWORDS


def test_common_prefix_len() -> None:
    """common_prefix_len counts matching prefix characters."""
    assert common_prefix_len("transporte", "transportar") == 9
    assert common_prefix_len("envio", "enviamo") == 4
    assert common_prefix_len("casa", "auto") == 0


def test_variant_best_exact_and_prefix() -> None:
    """variant_best scores 1.0 for exact stem matches and 0.7 for prefix >= 4 chars."""
    doc_stems = {"transportar", "tarifa", "bogota"}

    # Exact match
    assert variant_best("tarifa", doc_stems) == 1.0

    # Prefix match (>= 4 chars shared: 'transpor' in 'transportar' and 'transporte')
    assert variant_best("transporte", doc_stems) == 0.7

    # No match
    assert variant_best("reclamacion", doc_stems) == 0.0

    # Variant < 4 chars never prefix matches
    assert variant_best("tra", doc_stems) == 0.0


def test_lexical_evidence_on_domain_match() -> None:
    """Questions sharing content stems with the text return evidence > 0."""
    question = "¿Cuál es el costo del envío a Medellín?"
    chunk_text = "El costo del envío nacional hacia Medellín se calcula por kilo real."
    evidence = lexical_evidence(question, chunk_text)
    assert evidence > 0.0


def test_lexical_evidence_synonyms() -> None:
    """Synonyms defined in _STEM_EQUIVALENTS generate lexical evidence."""
    # 'costo' and 'precio' are synonyms
    assert "precio" in _STEM_EQUIVALENTS.get("costo", set())
    question = "¿Cuál es el precio del paquete?"
    chunk_text = "El costo base por encomienda es de quince mil pesos."
    evidence = lexical_evidence(question, chunk_text)
    assert evidence > 0.0


def test_lexical_evidence_off_domain_zero() -> None:
    """Completely off-domain questions return 0.0 lexical evidence."""
    question = "¿Quién ganó el mundial de fútbol en 1998?"
    chunk_text = "TransLogix presta servicios de paquetería y carga pesada en Colombia."
    assert lexical_evidence(question, chunk_text) == 0.0


def test_lexical_evidence_empty_inputs() -> None:
    """Empty question or empty chunk text returns 0.0."""
    assert lexical_evidence("", "Texto de prueba") == 0.0
    assert lexical_evidence("¿Cuál es el horario?", "") == 0.0
    assert lexical_evidence("   ", "   ") == 0.0
