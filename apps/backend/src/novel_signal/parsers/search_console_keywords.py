from __future__ import annotations

import json
from typing import Any

from novel_signal.parsers.base import ParsedEnvelope


class GoogleSearchConsoleKeywordParser:
    """Parse Search Analytics rows when the configured dimensions include ``query``."""

    platform = "google_search_console"
    page_type = "search_analytics"
    version = "google-search-console-search-analytics-v1"

    def __init__(self, *, dimensions: tuple[str, ...]) -> None:
        if "query" not in dimensions:
            raise ValueError("Google Search Console keyword parsing requires a query dimension")
        self.dimensions = dimensions
        self._query_index = dimensions.index("query")

    def parse(self, raw: bytes) -> ParsedEnvelope:
        payload = _json_object(raw)
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError("Google Search Console response rows must be a list")

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Google Search Console rows must be objects")
            keys = row.get("keys")
            if not isinstance(keys, list) or len(keys) <= self._query_index:
                warnings.append("Skipped Google Search Console row without a query key")
                continue
            query = _optional_string(keys[self._query_index])
            if query is None:
                warnings.append("Skipped Google Search Console row with a blank query")
                continue
            observation: dict[str, object] = {
                "dimensions": {
                    dimension: value
                    for dimension, value in zip(self.dimensions, keys, strict=False)
                    if isinstance(value, str)
                }
            }
            for field in ("clicks", "impressions", "ctr", "position"):
                value = row.get(field)
                if _is_number(value):
                    observation[field] = value
            records.append(
                {
                    "keyword_text": query,
                    "observation_metadata": observation,
                }
            )
        return ParsedEnvelope(
            parser_version=self.version,
            page_type=self.page_type,
            records=tuple(records),
            warnings=tuple(warnings),
        )


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Google Search Console response is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Google Search Console response must be a JSON object")
    return payload


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
