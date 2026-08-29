from __future__ import annotations

from collections.abc import Iterable

from novel_signal.modules.keywords.models import IntentCluster
from novel_signal.modules.keywords.schemas import normalize_keyword

_PROBLEM_BENEFIT_TERMS = frozenset(
    {
        "rash",
        "sensitive",
        "gentle",
        "dry",
        "comfort",
        "hypoallergenic",
        "protection",
        "absorbent",
    }
)


def classify_keyword_intent(
    keyword_text: str,
    *,
    owned_brands: Iterable[str],
    competitor_brands: Iterable[str],
    categories: Iterable[str],
) -> IntentCluster:
    """Classify a discovery term using explicit configured catalogue vocabulary.

    The classifier is intentionally conservative: unknown terms remain
    ``UNCLASSIFIED`` instead of receiving a fabricated business interpretation.
    """
    normalized = normalize_keyword(keyword_text)
    owned = _normalized_phrases(owned_brands)
    competitors = _normalized_phrases(competitor_brands)
    category_terms = _normalized_phrases(categories)

    if _contains_phrase(normalized, owned):
        return IntentCluster.OWN_BRAND
    if _contains_phrase(normalized, competitors):
        return IntentCluster.COMPETITOR_BRAND
    if any(term in normalized.split() for term in _PROBLEM_BENEFIT_TERMS):
        return IntentCluster.PROBLEM_BENEFIT
    if normalized in category_terms:
        return IntentCluster.GENERIC_CATEGORY
    return IntentCluster.UNCLASSIFIED


def _normalized_phrases(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({normalize_keyword(value) for value in values if value.strip()}))


def _contains_phrase(text: str, phrases: Iterable[str]) -> bool:
    padded = f" {text} "
    return any(f" {phrase} " in padded for phrase in phrases)
