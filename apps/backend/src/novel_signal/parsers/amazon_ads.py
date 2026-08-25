from __future__ import annotations

import gzip
import json
from typing import Any


class AmazonAdsReportParseError(ValueError):
    pass


def parse_report(body: bytes) -> tuple[dict[str, Any], ...]:
    if body.startswith(b"\x1f\x8b"):
        body = gzip.decompress(body)
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AmazonAdsReportParseError("Amazon Ads report is not valid JSON") from error
    if isinstance(payload, dict):
        payload = payload.get("rows", payload.get("data"))
    if not isinstance(payload, list):
        raise AmazonAdsReportParseError("Amazon Ads report did not contain rows")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise AmazonAdsReportParseError(f"Amazon Ads report row {index} is not an object")
        if not str(row.get("campaignId", "")).strip() or not str(row.get("searchTerm", "")).strip():
            raise AmazonAdsReportParseError(
                f"Amazon Ads report row {index} lacks campaignId or searchTerm"
            )
        rows.append(row)
    return tuple(rows)
