"""Deterministic parser for public Amazon India search-result HTML.

This parser is deliberately evidence-only: it neither fetches pages nor writes
database records.  It accepts a conservative subset of product-card structures
and skips cards whose marketplace identity cannot be established safely.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from novel_signal.parsers.base import ParsedEnvelope


class AmazonSerpParser:
    """Parse Amazon India public SERP cards into S3-compatible records."""

    platform = "amazon_in"
    page_type = "serp"
    version = "amazon-serp-v1"

    def __init__(self, *, page_number: int = 1) -> None:
        if page_number < 1:
            raise ValueError("Amazon SERP page number must be positive")
        self.page_number = page_number

    def parse(self, raw: bytes) -> ParsedEnvelope:
        if not raw:
            raise ValueError("Amazon SERP HTML is empty")
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Amazon SERP HTML is not valid UTF-8") from None

        document = _HtmlTreeParser()
        try:
            document.feed(html)
            document.close()
        except Exception:
            raise ValueError("Amazon SERP HTML could not be parsed") from None

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        cards = _product_cards(document.root)
        if not cards:
            warnings.append("No Amazon SERP product cards found")
        for card_index, card in enumerate(cards, start=1):
            asin = _extract_asin(card)
            if asin is None:
                warnings.append(f"Skipped Amazon SERP card {card_index} without a valid ASIN")
                continue
            records.append(
                _parse_card(
                    card,
                    asin=asin,
                    absolute_position=len(records) + 1,
                    page_number=self.page_number,
                    warnings=warnings,
                )
            )
        return ParsedEnvelope(
            parser_version=self.version,
            page_type=self.page_type,
            records=tuple(records),
            warnings=tuple(warnings),
        )


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text(self) -> str:
        return " ".join(
            piece
            for piece in (" ".join(self.text_parts), *(child.text() for child in self.children))
            if piece
        )

    def descendants(self) -> tuple[_Node, ...]:
        nodes: list[_Node] = []
        for child in self.children:
            nodes.append(child)
            nodes.extend(child.descendants())
        return tuple(nodes)


class _HtmlTreeParser(HTMLParser):
    """Small dependency-free tree builder for the selectors used below."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag.lower(), {name.lower(): value or "" for name, value in attrs})
        self._stack[-1].children.append(node)
        if tag.lower() not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized_tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        normalized = _clean_text(data)
        if normalized:
            self._stack[-1].text_parts.append(normalized)


_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}
_ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
_ASIN_LINK_PATTERN = re.compile(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)")
_MONEY_PATTERN = re.compile(
    r"₹\s*((?:\d{1,3}(?:,\d{2})*,\d{3}|\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?![\d,])"
)
_DISCOUNT_PATTERN = re.compile(
    r"(?:-|−)?\s*(\d{1,3}(?:\.\d+)?)\s*%(?:\s*off)?(?=\s|$)", re.IGNORECASE
)
_RATING_PATTERN = re.compile(r"(\d(?:\.\d+)?)\s*(?:out of\s*5\s*stars?)?", re.IGNORECASE)
_REVIEW_COUNT_PATTERN = re.compile(r"([0-9][0-9,]*)\s+(?:ratings|reviews)\b", re.IGNORECASE)
_AMAZONS_CHOICE_TERM_PATTERN = re.compile(
    r"amazon['’]s\s+choice\s+for\s+[\"“]([^\"”]+)[\"”]", re.IGNORECASE
)


def _product_cards(root: _Node) -> tuple[_Node, ...]:
    cards: list[_Node] = []

    def visit(node: _Node, *, inside_card: bool) -> None:
        is_card = _is_candidate(node)
        if is_card and not inside_card:
            cards.append(node)
        for child in node.children:
            visit(child, inside_card=inside_card or is_card)

    visit(root, inside_card=False)
    return tuple(cards)


def _is_candidate(node: _Node) -> bool:
    return (
        node.attrs.get("data-component-type", "").lower() == "s-search-result"
        or "data-asin" in node.attrs
    )


def _parse_card(
    card: _Node,
    *,
    asin: str,
    absolute_position: int,
    page_number: int,
    warnings: list[str],
) -> dict[str, Any]:
    card_text = _clean_text(card.text())
    placement_type, sponsored = _placement(card)
    badges, unmapped_badges = _badges(card, sponsored)
    primary_image_url = _primary_image_url(card)
    metadata: dict[str, object] = {}
    title = _first_text(card, _is_title)
    if title is not None:
        metadata["title"] = title
    if primary_image_url is not None:
        metadata["primary_image_url"] = primary_image_url
    component_type = _optional_text(card.attrs.get("data-component-type"))
    if component_type is not None:
        metadata["source_dom_marker"] = component_type
    if unmapped_badges:
        metadata["unmapped_badges"] = unmapped_badges
        warnings.append("Amazon SERP card contained unmapped badge text")

    return {
        "absolute_position": absolute_position,
        "page_number": page_number,
        "marketplace_product_id": asin,
        "brand": _first_value(card, ("data-brand",), _is_brand),
        "placement_type": placement_type,
        "badges": badges,
        "amazons_choice_term": _amazons_choice_term(card, card_text),
        "displayed_price": _displayed_price(card),
        "mrp": _mrp(card),
        "discount_percent": _discount(card, card_text),
        "coupon": _first_value(card, ("data-coupon",), _is_coupon),
        "delivery_promise": _first_value(card, ("data-delivery",), _is_delivery),
        "rating": _rating(card, card_text),
        "review_count": _review_count(card, card_text),
        "thumbnail_hash": _thumbnail_hash(primary_image_url),
        "result_metadata": metadata or None,
    }


def _extract_asin(card: _Node) -> str | None:
    for node in (card, *card.descendants()):
        asin = _valid_asin(node.attrs.get("data-asin"))
        if asin is not None:
            return asin
    for node in (card, *card.descendants()):
        if node.tag != "a":
            continue
        match = _ASIN_LINK_PATTERN.search(node.attrs.get("href", ""))
        if match is not None:
            asin = _valid_asin(match.group(1))
            if asin is not None:
                return asin
    return None


def _valid_asin(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized if _ASIN_PATTERN.fullmatch(normalized) else None


def _placement(card: _Node) -> tuple[str, bool]:
    marker = " ".join(
        value
        for node in (card, *card.descendants())
        for name, value in node.attrs.items()
        if name in {"data-component-type", "data-placement", "data-sponsored"}
    ).lower()
    evidence = f"{marker} {' '.join(_visible_texts(card)).lower()}"
    if "sponsored brand video" in evidence:
        return "sponsored_brand_video", True
    if "sponsored display" in evidence:
        return "sponsored_display", True
    if "sponsored brands" in evidence or "sponsored brand" in evidence:
        return "sponsored_brand", True
    if "sponsored" in evidence:
        return "sponsored_product", True
    if "editorial_or_deal" in marker:
        return "editorial_or_deal", False
    return "organic", False


def _badges(card: _Node, sponsored: bool) -> tuple[list[str], list[str]]:
    badges: list[str] = []
    if _has_badge_label(card, "best seller"):
        badges.append("best_seller")
    if _has_badge_label(card, "amazon's choice") or _has_badge_label(card, "amazon’s choice"):
        badges.append("amazons_choice")
    if _has_badge_label(card, "limited time deal"):
        badges.append("limited_time_deal")
    elif _has_badge_label(card, "deal"):
        badges.append("deal")
    if _has_badge_label(card, "new arrival"):
        badges.append("new_arrival")
    if sponsored:
        badges.append("sponsored")

    unmapped = []
    for node in (card, *card.descendants()):
        badge = _optional_text(node.attrs.get("data-badge"))
        if badge is not None and badge.lower() not in _KNOWN_BADGE_TEXT:
            unmapped.append(badge)
    return list(dict.fromkeys(badges)), list(dict.fromkeys(unmapped))


_KNOWN_BADGE_TEXT = {
    "best seller",
    "amazon's choice",
    "amazon’s choice",
    "deal",
    "limited time deal",
    "new arrival",
    "sponsored",
}


def _visible_texts(card: _Node) -> tuple[str, ...]:
    return tuple(
        value
        for node in (card, *card.descendants())
        if not node.children
        if (value := _optional_text(node.text())) is not None
    )


def _has_badge_label(card: _Node, label: str) -> bool:
    return any(
        text.lower() == label
        or (
            label in {"amazon's choice", "amazon’s choice"}
            and text.lower().startswith(f"{label} for")
        )
        for text in _visible_texts(card)
    )


def _displayed_price(card: _Node) -> Decimal | None:
    value = _first_attribute(card, ("data-price", "data-current-price"))
    if value is not None:
        return _money(value)
    return _first_money(card, lambda node: _is_price(node) and not _is_mrp(node))


def _mrp(card: _Node) -> Decimal | None:
    value = _first_attribute(card, ("data-mrp", "data-list-price"))
    if value is not None:
        return _money(value)
    return _first_money(card, _is_mrp)


def _discount(card: _Node, card_text: str) -> Decimal | None:
    value = _first_attribute(card, ("data-discount",))
    return _percent(value) if value is not None else _percent(card_text)


def _rating(card: _Node, card_text: str) -> Decimal | None:
    value = _first_attribute(card, ("data-rating",))
    if value is None:
        value = _first_text(
            card, lambda node: _has_class(node, "a-icon-alt") or _has_class(node, "rating")
        )
    if value is not None:
        return _rating_value(value)
    match = re.search(r"\d(?:\.\d+)?\s+out of\s*5\s*stars?", card_text, re.IGNORECASE)
    return _rating_value(match.group(0)) if match is not None else None


def _review_count(card: _Node, card_text: str) -> int | None:
    value = _first_attribute(card, ("data-review-count",))
    if value is not None:
        return _integer(value)
    match = _REVIEW_COUNT_PATTERN.search(card_text)
    return _integer(match.group(1)) if match is not None else None


def _amazons_choice_term(card: _Node, card_text: str) -> str | None:
    explicit = _first_attribute(card, ("data-amazons-choice-term",))
    if explicit is not None:
        return _optional_text(explicit)
    match = _AMAZONS_CHOICE_TERM_PATTERN.search(card_text)
    return _optional_text(match.group(1)) if match is not None else None


def _primary_image_url(card: _Node) -> str | None:
    for node in (card, *card.descendants()):
        if node.tag != "img":
            continue
        url = _normalize_image_url(node.attrs.get("src"))
        if url is not None:
            return url
    return None


def _thumbnail_hash(url: str | None) -> str | None:
    return hashlib.sha256(url.encode("utf-8")).hexdigest() if url is not None else None


def _normalize_image_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _first_value(
    card: _Node,
    attributes: tuple[str, ...],
    selector: Any,
) -> str | None:
    value = _first_attribute(card, attributes)
    return _optional_text(value) if value is not None else _first_text(card, selector)


def _first_attribute(card: _Node, names: tuple[str, ...]) -> str | None:
    for node in (card, *card.descendants()):
        for name in names:
            value = node.attrs.get(name)
            if _optional_text(value) is not None:
                return value
    return None


def _first_text(card: _Node, selector: Any) -> str | None:
    for node in (card, *card.descendants()):
        if selector(node):
            value = _optional_text(node.text())
            if value is not None:
                return value
    return None


def _first_money(card: _Node, selector: Any) -> Decimal | None:
    for node in (card, *card.descendants()):
        if selector(node):
            value = _money(node.text())
            if value is not None:
                return value
    return None


def _has_class(node: _Node, expected: str) -> bool:
    return expected in node.attrs.get("class", "").lower().split()


def _is_price(node: _Node) -> bool:
    return any(token.startswith("a-price") for token in node.attrs.get("class", "").lower().split())


def _is_mrp(node: _Node) -> bool:
    class_name = node.attrs.get("class", "").lower()
    return any(marker in class_name for marker in ("a-text-price", "mrp", "list-price")) or any(
        key in node.attrs for key in ("data-mrp", "data-list-price")
    )


def _is_title(node: _Node) -> bool:
    return (
        "data-title" in node.attrs
        or "title" in node.attrs.get("class", "").lower().split()
        or node.tag == "h2"
    )


def _is_brand(node: _Node) -> bool:
    return "brand" in node.attrs.get("class", "").lower().split()


def _is_coupon(node: _Node) -> bool:
    return "coupon" in node.attrs.get("class", "").lower().split()


def _is_delivery(node: _Node) -> bool:
    return "delivery" in node.attrs.get("class", "").lower().split()


def _money(value: str) -> Decimal | None:
    match = _MONEY_PATTERN.search(value)
    if match is None:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def _percent(value: str) -> Decimal | None:
    match = _DISCOUNT_PATTERN.search(value)
    if match is None:
        return None
    try:
        result = Decimal(match.group(1))
    except InvalidOperation:
        return None
    return result if Decimal("0") <= result <= Decimal("100") else None


def _rating_value(value: str) -> Decimal | None:
    match = _RATING_PATTERN.search(value)
    if match is None:
        return None
    try:
        result = Decimal(match.group(1))
    except InvalidOperation:
        return None
    return result if Decimal("0") <= result <= Decimal("5") else None


def _integer(value: str) -> int | None:
    normalized = value.replace(",", "").strip()
    return int(normalized) if normalized.isdigit() else None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _clean_text(value)
    return normalized or None


def _clean_text(value: str) -> str:
    return " ".join(value.split())
