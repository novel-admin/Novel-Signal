from __future__ import annotations

import hashlib
import html
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from novel_signal.modules.rank_visibility.models import BadgeType, PlacementType
from novel_signal.parsers.base import ParsedEnvelope


class AmazonSearchParser:
    """Small, versioned parser for stable ASIN/result markers in Amazon search HTML."""

    platform = "amazon_in"
    page_type = "serp"
    version = "amazon-serp-v1"

    _result = re.compile(
        r'<div[^>]+data-asin=["\'](?P<asin>[A-Z0-9]{10})["\'][^>]*>(?P<body>.*?)</div>',
        re.I | re.S,
    )
    _tag = re.compile(r"<[^>]+>")

    def parse(self, raw: bytes) -> ParsedEnvelope:
        source = raw.decode("utf-8", errors="replace")
        records: list[dict[str, Any]] = []
        for position, match in enumerate(self._result.finditer(source), start=1):
            body = match.group("body")
            text = self._text(body)
            placement = (
                PlacementType.SPONSORED_PRODUCT
                if "sponsored" in text.lower() or "sponsored" in body.lower()
                else PlacementType.ORGANIC
            )
            record: dict[str, Any] = {
                "absolute_position": position,
                "within_type_position": None,
                "page_number": 1,
                "marketplace_product_id": match.group("asin").upper(),
                "brand": self._brand(body),
                "placement_type": placement,
                "badges": self._badges(text),
                "rating": self._decimal(self._first(r"([0-5](?:\.[0-9])?) out of 5", text)),
                "review_count": self._integer(self._first(r"([\d,]+) ratings?", text)),
                "displayed_price": self._decimal(
                    self._first(r"(?:₹|rs\.?)[ ]*([\d,]+(?:\.[0-9]{1,2})?)", text)
                ),
                "result_metadata": {
                    "title": text[:500] or None,
                    "source": "amazon_public_search_html",
                },
            }
            records.append(record)
        return ParsedEnvelope(
            parser_version=self.version,
            page_type=self.page_type,
            records=tuple(records),
            warnings=(
                "Amazon HTML is layout-sensitive; inspect raw evidence when fields are missing",
            ),
        )

    def _text(self, value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(self._tag.sub(" ", value))).strip()

    def _brand(self, body: str) -> str | None:
        match = re.search(r"(?:brand|byline)[^>]{0,120}>([^<]{2,80})<", body, re.I)
        return self._text(match.group(1)) if match else None

    @staticmethod
    def _first(pattern: str, value: str) -> str | None:
        match = re.search(pattern, value, re.I)
        return match.group(1) if match else None

    @staticmethod
    def _decimal(value: str | None) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(value.replace(",", ""))
        except InvalidOperation:
            return None

    @staticmethod
    def _integer(value: str | None) -> int | None:
        return int(value.replace(",", "")) if value else None

    @staticmethod
    def _badges(text: str) -> list[BadgeType]:
        lowered = text.lower()
        badges: list[BadgeType] = []
        if "amazon's choice" in lowered or "amazons choice" in lowered:
            badges.append(BadgeType.AMAZONS_CHOICE)
        if "best seller" in lowered:
            badges.append(BadgeType.BEST_SELLER)
        if "deal" in lowered:
            badges.append(BadgeType.DEAL)
        if "sponsored" in lowered:
            badges.append(BadgeType.SPONSORED)
        return badges


class AmazonProductParser:
    platform = "amazon_in"
    page_type = "product_detail"
    version = "amazon-product-v1"

    def parse(self, raw: bytes) -> ParsedEnvelope:
        source = raw.decode("utf-8", errors="replace")
        asin = AmazonSearchParser._first(r'id=["\']ASIN["\'][^>]*value=["\']([A-Z0-9]{10})', source)
        if not asin:
            asin = AmazonSearchParser._first(r'"asin"\s*:\s*"([A-Z0-9]{10})"', source)
        if not asin:
            return ParsedEnvelope(self.version, self.page_type, ())
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", source))).strip()
        title = AmazonSearchParser._first(
            r'<span[^>]+id=["\']productTitle["\'][^>]*>(.*?)</span>', source
        )
        rating = AmazonSearchParser._decimal(
            AmazonSearchParser._first(r"([0-5](?:\.[0-9])?) out of 5", text)
        )
        review_count = AmazonSearchParser._integer(
            AmazonSearchParser._first(r"([\d,]+) ratings?", text)
        )
        record = {
            "marketplace_product_id": asin.upper(),
            "title": title,
            "rating": rating,
            "review_count": review_count,
            "content_hash": hashlib.sha256(raw).hexdigest(),
        }
        return ParsedEnvelope(self.version, self.page_type, (record,))
