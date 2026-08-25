from __future__ import annotations

import json
from typing import Any

from novel_signal.parsers.base import ParsedEnvelope


class BrandAnalyticsSearchQueryPerformanceParser:
    """Parse Amazon's ``sellingPartnerSearchQueryPerformanceReport.json`` schema."""

    platform = "amazon_brand_analytics"
    page_type = "brand_analytics_search_query_performance"
    version = "brand-analytics-search-query-performance-v2"

    def parse(self, raw: bytes) -> ParsedEnvelope:
        payload = _json_object(raw)
        report_specification = _required_object(payload, "reportSpecification")
        if report_specification.get("reportType") != _REPORT_TYPE:
            raise ValueError("Brand Analytics reportType is not Search Query Performance")
        report_options = _required_object(report_specification, "reportOptions")
        data_by_asin = payload.get("dataByAsin")
        if not isinstance(data_by_asin, list):
            raise ValueError("Brand Analytics report must contain a dataByAsin list")

        report_context: dict[str, object] = {}
        _copy_string(report_context, "report_period", report_options.get("reportPeriod"))
        _copy_string(report_context, "report_asins", report_options.get("asin"))
        _copy_string(report_context, "report_start_date", report_specification.get("dataStartTime"))
        _copy_string(report_context, "report_end_date", report_specification.get("dataEndTime"))
        marketplace_ids = report_specification.get("marketplaceIds")
        if isinstance(marketplace_ids, list) and all(
            isinstance(marketplace_id, str) for marketplace_id in marketplace_ids
        ):
            report_context["marketplace_ids"] = marketplace_ids

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        for entry in data_by_asin:
            if not isinstance(entry, dict):
                raise ValueError("Brand Analytics dataByAsin entries must be objects")
            search_query_data = _required_object(entry, "searchQueryData")
            query = _optional_string(search_query_data.get("searchQuery"))
            if query is None:
                warnings.append("Skipped Brand Analytics row without a usable searchQuery")
                continue

            observation = dict(report_context)
            _copy_string(observation, "asin", entry.get("asin"))
            _copy_string(observation, "start_date", entry.get("startDate"))
            _copy_string(observation, "end_date", entry.get("endDate"))
            _copy_metrics(
                observation,
                search_query_data,
                (
                    ("searchQueryScore", "search_query_score"),
                    ("searchQueryVolume", "search_query_volume"),
                ),
            )
            _copy_metrics(
                observation,
                entry.get("impressionData"),
                (
                    ("totalQueryImpressionCount", "total_query_impression_count"),
                    ("asinImpressionCount", "asin_impression_count"),
                    ("asinImpressionShare", "asin_impression_share"),
                ),
            )
            _copy_metrics(observation, entry.get("clickData"), _FUNNEL_METRICS["click"])
            _copy_metrics(observation, entry.get("cartAddData"), _FUNNEL_METRICS["cart_add"])
            _copy_metrics(observation, entry.get("purchaseData"), _FUNNEL_METRICS["purchase"])
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


_REPORT_TYPE = "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT"
_FUNNEL_METRICS = {
    "click": (
        ("totalClickCount", "total_click_count"),
        ("totalClickRate", "total_click_rate"),
        ("asinClickCount", "asin_click_count"),
        ("asinClickShare", "asin_click_share"),
        ("totalSameDayShippingClickCount", "total_same_day_shipping_click_count"),
        ("totalOneDayShippingClickCount", "total_one_day_shipping_click_count"),
        ("totalTwoDayShippingClickCount", "total_two_day_shipping_click_count"),
    ),
    "cart_add": (
        ("totalCartAddCount", "total_cart_add_count"),
        ("totalCartAddRate", "total_cart_add_rate"),
        ("asinCartAddCount", "asin_cart_add_count"),
        ("asinCartAddShare", "asin_cart_add_share"),
        ("totalSameDayShippingCartAddCount", "total_same_day_shipping_cart_add_count"),
        ("totalOneDayShippingCartAddCount", "total_one_day_shipping_cart_add_count"),
        ("totalTwoDayShippingCartAddCount", "total_two_day_shipping_cart_add_count"),
    ),
    "purchase": (
        ("totalPurchaseCount", "total_purchase_count"),
        ("totalPurchaseRate", "total_purchase_rate"),
        ("asinPurchaseCount", "asin_purchase_count"),
        ("asinPurchaseShare", "asin_purchase_share"),
        ("totalSameDayShippingPurchaseCount", "total_same_day_shipping_purchase_count"),
        ("totalOneDayShippingPurchaseCount", "total_one_day_shipping_purchase_count"),
        ("totalTwoDayShippingPurchaseCount", "total_two_day_shipping_purchase_count"),
    ),
}


def _json_object(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Brand Analytics report is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Brand Analytics report must be a JSON object")
    return payload


def _required_object(parent: dict[str, Any], field: str) -> dict[str, Any]:
    value = parent.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"Brand Analytics report must contain an object {field}")
    return value


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _copy_string(target: dict[str, object], field: str, value: object) -> None:
    normalized = _optional_string(value)
    if normalized is not None:
        target[field] = normalized


def _copy_metrics(
    target: dict[str, object],
    source: object,
    fields: tuple[tuple[str, str], ...],
) -> None:
    if not isinstance(source, dict):
        return
    for source_field, normalized_field in fields:
        value = source.get(source_field)
        if _is_number(value):
            target[normalized_field] = value


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
