"""Deterministic parser for public Amazon India product-detail HTML.

The parser is deliberately evidence-only. It accepts raw HTML bytes, extracts a
conservative normalized record for later S5/S6 publication, and never fetches,
persists, or executes page content.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from novel_signal.parsers.base import ParsedEnvelope

_ASIN = re.compile(r"^[A-Z0-9]{10}$")
_ASIN_LINK = re.compile(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)")
_MONEY = re.compile(r"(?:₹|Rs\.?\s*)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.IGNORECASE)
_PERCENT = re.compile(r"(?:-|−)?\s*(\d{1,3}(?:\.\d+)?)\s*%\s*(?:off)?\b", re.IGNORECASE)
_PACK = re.compile(r"\bpack\s+of\s+(\d+)\b", re.IGNORECASE)
_COUNT = re.compile(r"\b(\d+)\s*(?:count|pcs?|pieces?)\b", re.IGNORECASE)
_UNIT = re.compile(r"\b(\d+(?:\.\d+)?)\s*(ml|l|g|kg|count|pcs?|pieces?)\b", re.IGNORECASE)


class AmazonProductParser:
    platform = "amazon_in"
    page_type = "product_detail"
    version = "amazon-product-v1"

    def parse(self, raw: bytes) -> ParsedEnvelope:
        if not raw:
            raise ValueError("Amazon product HTML is empty")
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Amazon product HTML is not valid UTF-8") from None

        document = _DocumentParser()
        try:
            document.feed(html)
            document.close()
        except Exception:
            raise ValueError("Amazon product HTML could not be parsed") from None

        nodes = tuple(document.root.walk())
        asin = _asin(nodes)
        if asin is None:
            raise ValueError("Amazon product identity is unavailable")

        warnings: list[str] = []
        title = _text_for_id(nodes, "productTitle")
        brand = _brand(nodes)
        bullets = _bullets(nodes)
        description = _text_for_id(nodes, "productDescription")
        images = _images(nodes)
        a_plus_sections = _a_plus_sections(nodes)
        video_count = _video_count(nodes)
        variation_metadata = _variations(nodes)
        primary_price = _primary_price(nodes, warnings)
        mrp = _mrp(nodes, warnings)
        coupon_text = _coupon_text(nodes)
        coupon_value, coupon_type = _coupon(coupon_text)
        availability = _availability(nodes)
        shipping = _shipping(nodes, warnings)
        offers = _offers(nodes, availability)
        seller_name, seller_id = _primary_seller(nodes)
        featured = _featured_offer(nodes)
        metadata = _content_metadata(nodes)

        image_hashes = [hashlib.sha256(url.encode("utf-8")).hexdigest() for url in images]
        record: dict[str, Any] = {
            "marketplace_product_id": asin,
            "title": title,
            "brand": brand,
            "category_path": _category_path(nodes),
            "description": description,
            "bullets": bullets,
            "key_features": list(bullets),
            "a_plus_present": bool(a_plus_sections),
            "a_plus_sections": a_plus_sections,
            "image_urls": images,
            "image_hashes": image_hashes,
            "image_count": len(images),
            "video_present": video_count > 0,
            "video_count": video_count,
            "variation_count": _variation_count(variation_metadata),
            "variation_metadata": variation_metadata or None,
            "storefront_text": _storefront_text(nodes),
            "content_metadata": metadata or None,
            "availability_status": availability,
            "primary_price": primary_price,
            "mrp": mrp,
            "discount_percent": _discount(nodes),
            "coupon_text": coupon_text,
            "coupon_value": coupon_value,
            "coupon_type": coupon_type,
            "shipping_amount": shipping,
            "effective_price": _effective_price(nodes, warnings),
            "primary_seller_name": seller_name,
            "primary_seller_id": seller_id,
            "is_featured_offer": featured,
            "seller_count": len(offers) if offers else None,
            "offers": offers,
        }
        return ParsedEnvelope(
            parser_version=self.version,
            page_type=self.page_type,
            records=(record,),
            warnings=tuple(warnings),
        )


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text(self) -> str:
        return _clean(" ".join((*self.text_parts, *(child.text() for child in self.children))))

    def walk(self) -> tuple[_Node, ...]:
        result: list[_Node] = [self]
        for child in self.children:
            result.extend(child.walk())
        return tuple(result)


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self._stack = [self.root]
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"}:
            self._ignored_depth += 1
        node = _Node(normalized, {key.lower(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if normalized not in _VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized:
                del self._stack[index:]
                break
        if normalized in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            cleaned = _clean(data)
            if cleaned:
                self._stack[-1].text_parts.append(cleaned)


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}


def _clean(value: str) -> str:
    return " ".join(value.split())


def _nodes_with_id(nodes: tuple[_Node, ...], identifier: str) -> tuple[_Node, ...]:
    return tuple(node for node in nodes if node.attrs.get("id", "").lower() == identifier.lower())


def _text_for_id(nodes: tuple[_Node, ...], identifier: str) -> str | None:
    return _first_text(_nodes_with_id(nodes, identifier))


def _first_text(nodes: tuple[_Node, ...]) -> str | None:
    for node in nodes:
        text = node.text()
        if text:
            return text
    return None


def _asin(nodes: tuple[_Node, ...]) -> str | None:
    for node in nodes:
        for name in ("data-asin", "data-product-asin", "value", "content"):
            if name in node.attrs and (
                node.attrs.get("id", "").lower() == "asin"
                or node.attrs.get("name", "").lower() in {"asin", "asin.0"}
                or name.startswith("data-")
                or node.attrs.get("name", "").lower() == "asin"
            ):
                parsed = _valid_asin(node.attrs[name])
                if parsed:
                    return parsed
    for node in nodes:
        if node.tag == "a":
            match = _ASIN_LINK.search(node.attrs.get("href", ""))
            if match:
                return _valid_asin(match.group(1))
    return None


def _valid_asin(value: str) -> str | None:
    normalized = value.strip().upper()
    return normalized if _ASIN.fullmatch(normalized) else None


def _brand(nodes: tuple[_Node, ...]) -> str | None:
    text = _text_for_id(nodes, "bylineInfo")
    if text is None:
        for node in nodes:
            if node.attrs.get("itemprop", "").lower() in {"brand", "manufacturer"}:
                text = node.attrs.get("content") or node.text()
                if text:
                    break
    if text is None:
        return None
    normalized = re.sub(r"^brand\s*:\s*", "", text, flags=re.IGNORECASE)
    match = re.fullmatch(r"Visit the (.+?) Store", normalized, flags=re.IGNORECASE)
    return _clean(match.group(1) if match else normalized) or None


def _category_path(nodes: tuple[_Node, ...]) -> str | None:
    breadcrumb = _nodes_with_id(nodes, "wayfinding-breadcrumbs_container")
    if not breadcrumb:
        return None
    values = _ordered_unique(
        child.text() for node in breadcrumb for child in node.walk() if child.tag == "a"
    )
    return " > ".join(values) or None


def _bullets(nodes: tuple[_Node, ...]) -> list[str]:
    blocks = _nodes_with_id(nodes, "feature-bullets")
    return _ordered_unique(
        item.text() for block in blocks for item in block.walk() if item.tag == "li"
    )


def _a_plus_sections(nodes: tuple[_Node, ...]) -> list[object]:
    blocks = tuple(
        node
        for node in nodes
        if "aplus" in node.attrs.get("id", "").lower()
        or "aplus" in node.attrs.get("data-cel-widget", "").lower()
        or "aplus" in node.attrs.get("class", "").lower()
    )
    summaries: list[object] = []
    for block in blocks:
        text = block.text()
        if text:
            summaries.append({"text": text})
    return _ordered_unique_objects(summaries)


def _images(nodes: tuple[_Node, ...]) -> list[str]:
    candidates: list[str] = []
    for node in nodes:
        node_id = node.attrs.get("id", "").lower()
        node_class = node.attrs.get("class", "").lower()
        product_evidence = (
            node_id in {"landingimage", "imgtagwrapperid"}
            or "imageblock" in node_id
            or "image" in node_class and "product" in node_class
            or "data-a-dynamic-image" in node.attrs
        )
        if not product_evidence:
            continue
        candidates.extend(_urls_from_node(node))
    return _ordered_unique(_normalize_url(url) for url in candidates if _normalize_url(url))


def _urls_from_node(node: _Node) -> list[str]:
    result = [
        node.attrs[name]
        for name in ("data-old-hires", "src", "data-image-url")
        if node.attrs.get(name)
    ]
    dynamic = node.attrs.get("data-a-dynamic-image")
    if dynamic:
        try:
            decoded = json.loads(dynamic)
        except json.JSONDecodeError:
            return result
        if isinstance(decoded, dict):
            result.extend(str(url) for url in decoded if isinstance(url, str))
    return result


def _normalize_url(url: str) -> str | None:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _video_count(nodes: tuple[_Node, ...]) -> int:
    """Count explicit video elements/markers, never repeated container text."""
    identities: set[str] = set()
    for index, node in enumerate(nodes):
        explicit_marker = node.tag == "video" or "data-video" in node.attrs
        if not explicit_marker:
            continue
        if node.tag != "video" and any(child.tag == "video" for child in node.walk()[1:]):
            continue
        identity = (
            node.attrs.get("data-video-id")
            or node.attrs.get("src")
            or node.attrs.get("id")
            or node.attrs.get("data-video")
            or str(index)
        )
        identities.add(identity)
    return len(identities)


def _variations(nodes: tuple[_Node, ...]) -> dict[str, object]:
    dimensions: dict[str, list[str]] = {}
    for node in nodes:
        identifier = node.attrs.get("id", "")
        match = re.match(r"variation_(.+)", identifier, flags=re.IGNORECASE)
        if not match:
            continue
        values = _ordered_unique(
            child.attrs.get("title") or child.attrs.get("value") or child.text()
            for child in node.walk()
            if child.tag in {"li", "option", "button"}
        )
        if values:
            dimensions[match.group(1).lower()] = values
    return {"dimensions": dimensions} if dimensions else {}


def _variation_count(metadata: dict[str, object]) -> int | None:
    """Count distinct visible option labels, not Cartesian variation combinations."""
    dimensions = metadata.get("dimensions")
    if not isinstance(dimensions, dict):
        return None
    choices = {
        value
        for values in dimensions.values()
        if isinstance(values, list)
        for value in values
        if isinstance(value, str)
    }
    return len(choices)


def _primary_price(nodes: tuple[_Node, ...], warnings: list[str]) -> Decimal | None:
    preferred = ("priceblock_dealprice", "priceblock_ourprice", "priceblock_saleprice", "coreprice")
    for identifier in preferred:
        value = _money(_text_for_id(nodes, identifier))
        if value is not None:
            return value
    for node in nodes:
        classes = node.attrs.get("class", "").lower()
        if "a-price" in classes and "basisprice" not in classes:
            value = _money(node.text())
            if value is not None:
                return value
    if any("price" in node.attrs.get("id", "").lower() for node in nodes):
        warnings.append("Malformed primary price ignored")
    return None


def _mrp(nodes: tuple[_Node, ...], warnings: list[str]) -> Decimal | None:
    for identifier in ("priceblock_listprice", "listPrice", "mrp"):
        value = _money(_text_for_id(nodes, identifier))
        if value is not None:
            return value
    for node in nodes:
        text = node.text()
        if re.search(r"\b(?:M\.R\.P\.?|MRP|list price)\b", text, re.IGNORECASE):
            value = _money(text)
            if value is not None:
                return value
    return None


def _money(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = _MONEY.search(value)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def _discount(nodes: tuple[_Node, ...]) -> Decimal | None:
    for node in nodes:
        if "discount" in node.attrs.get("class", "").lower() or "%" in node.text():
            match = _PERCENT.search(node.text())
            if match:
                value = Decimal(match.group(1))
                if Decimal("0") <= value <= Decimal("100"):
                    return value
    return None


def _coupon_text(nodes: tuple[_Node, ...]) -> str | None:
    for node in nodes:
        if (
            "coupon" in node.attrs.get("id", "").lower()
            or "coupon" in node.attrs.get("class", "").lower()
        ):
            text = node.text()
            if text:
                return text
    return None


def _coupon(text: str | None) -> tuple[Decimal | None, str | None]:
    if text is None:
        return None, None
    money = _money(text)
    if money is not None:
        return money, "absolute"
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return Decimal(match.group(1)), "percentage"
    return None, "uncertain"


def _shipping(nodes: tuple[_Node, ...], warnings: list[str]) -> Decimal | None:
    for node in nodes:
        identifier = f"{node.attrs.get('id', '')} {node.attrs.get('class', '')}".lower()
        if "delivery" not in identifier and "shipping" not in identifier:
            continue
        text = node.text()
        if "free delivery" in text.lower() or "free shipping" in text.lower():
            return Decimal("0")
        value = _money(text)
        if value is not None:
            return value
    return None


def _effective_price(nodes: tuple[_Node, ...], warnings: list[str]) -> Decimal | None:
    for node in nodes:
        marker = f"{node.attrs.get('id', '')} {node.attrs.get('class', '')} {node.text()}".lower()
        if "effective price" in marker or "net price" in marker:
            return _money(node.text())
    return None


def _availability(nodes: tuple[_Node, ...]) -> str:
    text = " ".join(
        node.text()
        for node in nodes
        if node.attrs.get("id", "").lower() == "availability"
        or "availability" in node.attrs.get("class", "").lower()
    ).lower()
    if "out of stock" in text:
        return "out_of_stock"
    if "unavailable" in text:
        return "unavailable"
    if "limited stock" in text or "only" in text and "left" in text:
        return "limited"
    if "in stock" in text or "available" in text:
        return "available"
    return "unknown"


def _primary_seller(nodes: tuple[_Node, ...]) -> tuple[str | None, str | None]:
    for node in nodes:
        if node.attrs.get("id", "").lower() != "sellerprofiletriggerid":
            continue
        seller_id = _seller_id(node.attrs.get("href", ""))
        return node.text() or None, seller_id
    for node in nodes:
        text = node.text()
        match = re.search(r"\bSold by\s+(.+?)(?:\s{2,}|$)", text, re.IGNORECASE)
        if match:
            return _clean(match.group(1)), _seller_id(node.attrs.get("href", ""))
    return None, None


def _seller_id(url: str) -> str | None:
    values = parse_qs(urlsplit(url).query).get("seller")
    return values[0] if values and values[0].strip() else None


def _featured_offer(nodes: tuple[_Node, ...]) -> bool | None:
    for node in nodes:
        explicit = node.attrs.get("data-featured-offer", "").strip().lower()
        if explicit in {"false", "no", "0"}:
            return False
        marker = f"{explicit} {node.text()}".lower()
        if "not featured offer" in marker or "not a featured offer" in marker:
            return False
        if "featured offer" in marker or "buy box" in marker:
            return True
    return None


def _offers(nodes: tuple[_Node, ...], availability: str) -> list[dict[str, object]]:
    offers: list[dict[str, object]] = []
    for node in nodes:
        marker = " ".join(
            (
                node.attrs.get("data-offer", ""),
                node.attrs.get("class", ""),
                node.attrs.get("id", ""),
            )
        ).lower()
        if "data-offer" not in node.attrs and "offer" not in marker:
            continue
        seller_node = next(
            (child for child in node.walk() if "seller" in child.attrs.get("class", "").lower()),
            None,
        )
        seller_name = seller_node.text() if seller_node else None
        seller_id = _seller_id(seller_node.attrs.get("href", "") if seller_node else "")
        if not seller_name:
            continue
        coupon_text = _coupon_text(node.walk())
        coupon_value, _ = _coupon(coupon_text)
        offer_availability = _availability(node.walk())
        offer: dict[str, object] = {
            "seller_name": seller_name,
            "seller_id": seller_id,
            "offer_price": _offer_price(node),
            "list_price": _mrp(node.walk(), []),
            "shipping_amount": _shipping(node.walk(), []),
            "coupon_text": coupon_text,
            "coupon_value": coupon_value,
            "effective_price": _effective_price(node.walk(), []),
            "availability_status": (
                offer_availability if offer_availability != "unknown" else availability
            ),
            "fulfillment_type": "amazon" if "fulfilled by amazon" in node.text().lower() else None,
            "is_featured_offer": _featured_offer(node.walk()),
            "prime_eligible": True if "prime" in node.text().lower() else None,
            "offer_metadata": None,
        }
        offers.append(offer)
    unique: list[dict[str, object]] = []
    identities: set[str] = set()
    for offer in offers:
        identity = str(offer["seller_id"] or offer["seller_name"]).casefold()
        if identity not in identities:
            identities.add(identity)
            unique.append(offer)
    return unique


def _offer_price(node: _Node) -> Decimal | None:
    """Read only explicit offer-price fields; containers are not price evidence."""
    for child in node.walk():
        marker = " ".join(
            (
                child.attrs.get("id", ""),
                child.attrs.get("class", ""),
                child.attrs.get("data-offer-price", ""),
            )
        ).lower()
        if "data-offer-price" not in child.attrs and not re.search(
            r"\boffer[-_ ]?price\b", marker
        ):
            continue
        if any(
            excluded in marker for excluded in ("list", "mrp", "coupon", "shipping", "delivery")
        ):
            continue
        value = _money(child.attrs.get("data-offer-price")) or _money(child.text())
        if value is not None:
            return value
    return None


def _content_metadata(nodes: tuple[_Node, ...]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    text = " ".join(
        node.text()
        for node in nodes
        if "detailbullets" in node.attrs.get("id", "").lower()
        or "productdetails" in node.attrs.get("id", "").lower()
    )
    bsr = re.search(
        r"Best Sellers Rank\s*:?\s*#([0-9,]+)(?:\s+in\s+([^#]+?))?(?:\s*#|$)",
        text,
        re.IGNORECASE,
    )
    if bsr:
        metadata["bsr"] = {
            "rank": int(bsr.group(1).replace(",", "")),
            "category": _clean(bsr.group(2) or "") or None,
        }
    pack = _PACK.search(text) or _COUNT.search(text)
    if pack:
        metadata["pack_quantity"] = int(pack.group(1))
    unit = _UNIT.search(text)
    if unit:
        metadata["pack_unit"] = unit.group(2).lower().rstrip(".")
        metadata["pack_unit_quantity"] = unit.group(1)
    return metadata


def _storefront_text(nodes: tuple[_Node, ...]) -> str | None:
    text = _text_for_id(nodes, "bylineInfo")
    return text if text and "store" in text.lower() else None


def _ordered_unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _clean(str(value))
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _ordered_unique_objects(values: list[object]) -> list[object]:
    seen: set[str] = set()
    result: list[object] = []
    for value in values:
        key = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
