"""Amazon Brand Analytics report-workflow access verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from novel_signal.config import Settings, get_settings
from novel_signal.sources.amazon.sp_api import AmazonSpApiClient, AmazonSpApiConfig
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.AMAZON_BRAND_ANALYTICS
_REPORTS_PATH = "/reports/2021-06-30/reports"
_SEARCH_QUERY_PERFORMANCE_REPORT = "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT"


class BrandAnalyticsError(RuntimeError):
    """Base error raised while verifying Brand Analytics report access."""


class BrandAnalyticsPermissionError(BrandAnalyticsError):
    """The seller account cannot request the permitted Brand Analytics report."""


class BrandAnalyticsAuthenticationError(BrandAnalyticsError):
    """Amazon rejected authentication for the Brand Analytics report request."""


class BrandAnalyticsRateLimitError(BrandAnalyticsError):
    """Amazon asked the caller to retry Brand Analytics verification later."""

    def __init__(self, retry_after: str | None) -> None:
        self.retry_after = retry_after
        delay = retry_after or "an unspecified delay"
        super().__init__(f"Amazon Brand Analytics rate limit; retry after {delay}.")


class BrandAnalyticsMalformedResponseError(BrandAnalyticsError):
    """The report-request response cannot establish report-workflow access."""


class BrandAnalyticsEmptyResponseError(BrandAnalyticsError):
    """Amazon accepted the request but returned no usable report identifier."""


class BrandAnalyticsNetworkError(BrandAnalyticsError):
    """The report-access verification request could not reach Amazon."""


class BrandAnalyticsUnsupportedOperationError(BrandAnalyticsError):
    """Collection is intentionally outside this verification-only slice."""


@dataclass(frozen=True)
class BrandAnalyticsConfig:
    """The existing SP-API configuration plus a permitted verification report type."""

    sp_api: AmazonSpApiConfig
    report_type: str = _SEARCH_QUERY_PERFORMANCE_REPORT

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> BrandAnalyticsConfig:
        current = settings or get_settings()
        return cls(AmazonSpApiConfig.from_settings(current))


class BrandAnalyticsClient:
    """Creates one minimal report request to prove Brand Analytics workflow access.

    A successful response only proves report-request permission. It does not poll,
    download, parse, persist, or claim that report data has been collected.
    """

    source_type = SOURCE_TYPE

    def __init__(
        self,
        config: BrandAnalyticsConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.config = config
        self._sp_api = AmazonSpApiClient(config.sp_api, transport=transport, timeout=timeout)
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def __aenter__(self) -> BrandAnalyticsClient:
        await self._sp_api.__aenter__()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()
        await self._sp_api.__aexit__()

    async def verify_connection(self) -> None:
        """Verify marketplace access and permission to request a BA report.

        The request uses a one-week date window and stops after receiving a report ID.
        It intentionally avoids polling, downloading, and parsing report data.
        """
        await self._sp_api.verify_connection()
        access_token = await self._sp_api.get_access_token()
        url = f"{self.config.sp_api.api_base_url.rstrip('/')}{_REPORTS_PATH}"
        headers = self._sp_api.signed_headers("POST", url, access_token)
        try:
            response = await self._client.post(url, headers=headers, json=self._request_payload())
        except httpx.TimeoutException as exc:
            raise BrandAnalyticsNetworkError(
                "Amazon Brand Analytics verification timed out."
            ) from exc
        except httpx.RequestError as exc:
            raise BrandAnalyticsNetworkError(
                "Amazon Brand Analytics verification request failed."
            ) from exc

        if response.status_code == 403:
            raise BrandAnalyticsPermissionError("Amazon Brand Analytics report access was denied.")
        if response.status_code == 429:
            raise BrandAnalyticsRateLimitError(response.headers.get("Retry-After"))
        if response.status_code == 401:
            raise BrandAnalyticsAuthenticationError(
                "Amazon Brand Analytics authentication was rejected."
            )
        if response.is_error:
            raise BrandAnalyticsError(
                "Amazon Brand Analytics verification request failed with status "
                f"{response.status_code}."
            )
        self._validate_report_response(response)

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        """Keep the source contract explicit until report ingestion is implemented."""
        del request
        raise BrandAnalyticsUnsupportedOperationError(
            "Amazon Brand Analytics collection is not implemented in this verification slice."
        )

    def _request_payload(self) -> dict[str, Any]:
        end = datetime.now(UTC).replace(microsecond=0)
        start = end - timedelta(days=7)
        return {
            "reportType": self.config.report_type,
            "marketplaceIds": [self.config.sp_api.marketplace_id],
            "dataStartTime": start.isoformat(),
            "dataEndTime": end.isoformat(),
        }

    @staticmethod
    def _validate_report_response(response: httpx.Response) -> None:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BrandAnalyticsMalformedResponseError(
                "Amazon Brand Analytics report response was not valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise BrandAnalyticsMalformedResponseError(
                "Amazon Brand Analytics report response was not a JSON object."
            )
        if not payload:
            raise BrandAnalyticsEmptyResponseError(
                "Amazon Brand Analytics report response was empty."
            )
        report_id = payload.get("reportId")
        if not isinstance(report_id, str) or not report_id.strip():
            raise BrandAnalyticsMalformedResponseError(
                "Amazon Brand Analytics report response did not contain a report ID."
            )
