"""Amazon Brand Analytics report-workflow access verification."""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from novel_signal.config import Settings, get_settings
from novel_signal.sources.amazon.sp_api import AmazonSpApiClient, AmazonSpApiConfig
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.AMAZON_BRAND_ANALYTICS
_REPORTS_PATH = "/reports/2021-06-30/reports"
_REPORT_DOCUMENTS_PATH = "/reports/2021-06-30/documents"
_SEARCH_QUERY_PERFORMANCE_REPORT = "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT"
_RAW_REPORT_RESOURCE = "brand_analytics_search_query_performance"


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


class BrandAnalyticsReportFailedError(BrandAnalyticsError):
    """Amazon terminated the requested report before it was available."""


class BrandAnalyticsPollingExhaustedError(BrandAnalyticsError):
    """Amazon did not complete the report within the configured polling bound."""


class BrandAnalyticsCursorError(BrandAnalyticsError):
    """The raw-report request does not identify a supported logical report window."""


class BrandAnalyticsCompressionError(BrandAnalyticsError):
    """The report document advertised unsupported or invalid compression."""


@dataclass(frozen=True)
class BrandAnalyticsConfig:
    """The existing SP-API configuration plus a permitted verification report type."""

    sp_api: AmazonSpApiConfig
    report_type: str = _SEARCH_QUERY_PERFORMANCE_REPORT
    poll_max_attempts: int = 5
    poll_interval_seconds: float = 0.0

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
        """Return one downloaded Brand Analytics document as an immutable raw page."""
        payload = self._fetch_payload(request)
        await self._sp_api.verify_connection()
        report = await self._sp_request("POST", _REPORTS_PATH, payload)
        report_id = self._required_string(report, "reportId", "report creation response")
        status = await self._poll_report(report_id)
        document_id = self._required_string(status, "reportDocumentId", "report status response")
        document = await self._sp_request("GET", f"{_REPORT_DOCUMENTS_PATH}/{document_id}")
        download_url = self._required_string(document, "url", "report document metadata")
        body, content_type = await self._download(
            download_url, document.get("compressionAlgorithm")
        )
        return (
            RawSourcePage(
                source=SOURCE_TYPE,
                resource_type=request.resource_type,
                body=body,
                content_type=content_type,
                request_fingerprint=self._fingerprint(request.resource_type, payload),
            ),
        )

    def _fetch_payload(self, request: SyncRequest) -> dict[str, Any]:
        if request.resource_type != _RAW_REPORT_RESOURCE or not isinstance(request.cursor, dict):
            raise BrandAnalyticsCursorError("Unsupported Brand Analytics raw-report request.")
        start = request.cursor.get("data_start_time")
        end = request.cursor.get("data_end_time")
        if not all(isinstance(value, str) and value.strip() for value in (start, end)):
            raise BrandAnalyticsCursorError(
                "Brand Analytics cursor requires data_start_time and data_end_time."
            )
        return {
            "reportType": self.config.report_type,
            "marketplaceIds": [self.config.sp_api.marketplace_id],
            "dataStartTime": start,
            "dataEndTime": end,
        }

    async def _poll_report(self, report_id: str) -> dict[str, Any]:
        for attempt in range(self.config.poll_max_attempts):
            status = await self._sp_request("GET", f"{_REPORTS_PATH}/{report_id}")
            processing_status = self._required_string(
                status, "processingStatus", "report status response"
            )
            if processing_status == "DONE":
                return status
            if processing_status in {"CANCELLED", "FATAL"}:
                raise BrandAnalyticsReportFailedError(
                    f"Amazon Brand Analytics report ended with {processing_status}."
                )
            if attempt < self.config.poll_max_attempts - 1 and self.config.poll_interval_seconds:
                await asyncio.sleep(self.config.poll_interval_seconds)
        raise BrandAnalyticsPollingExhaustedError(
            "Amazon Brand Analytics report polling was exhausted."
        )

    async def _sp_request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        token = await self._sp_api.get_access_token()
        url = f"{self.config.sp_api.api_base_url.rstrip('/')}{path}"
        try:
            response = await self._client.request(
                method, url, headers=self._sp_api.signed_headers(method, url, token), json=payload
            )
        except httpx.TimeoutException as exc:
            raise BrandAnalyticsNetworkError("Amazon Brand Analytics request timed out.") from exc
        except httpx.RequestError as exc:
            raise BrandAnalyticsNetworkError("Amazon Brand Analytics request failed.") from exc
        if response.status_code == 401:
            raise BrandAnalyticsAuthenticationError(
                "Amazon Brand Analytics authentication was rejected."
            )
        if response.status_code == 403:
            raise BrandAnalyticsPermissionError("Amazon Brand Analytics report access was denied.")
        if response.status_code == 429:
            raise BrandAnalyticsRateLimitError(response.headers.get("Retry-After"))
        if response.is_error:
            raise BrandAnalyticsError(
                f"Amazon Brand Analytics request failed with status {response.status_code}."
            )
        return self._json_object(response, "Amazon Brand Analytics response")

    async def _download(self, url: str, compression_algorithm: Any) -> tuple[bytes, str]:
        try:
            response = await self._client.get(url)
        except httpx.TimeoutException as exc:
            raise BrandAnalyticsNetworkError("Amazon report-document download timed out.") from exc
        except httpx.RequestError as exc:
            raise BrandAnalyticsNetworkError("Amazon report-document download failed.") from exc
        if response.is_error:
            raise BrandAnalyticsError(
                f"Amazon report-document download failed with status {response.status_code}."
            )
        if compression_algorithm is None:
            return response.content, response.headers.get(
                "content-type", "application/octet-stream"
            )
        if compression_algorithm != "GZIP":
            raise BrandAnalyticsCompressionError(
                "Amazon Brand Analytics report document uses unsupported compression."
            )
        try:
            return gzip.decompress(response.content), response.headers.get(
                "content-type", "application/octet-stream"
            )
        except OSError as exc:
            raise BrandAnalyticsCompressionError(
                "Amazon Brand Analytics report document contained invalid GZIP data."
            ) from exc

    @staticmethod
    def _fingerprint(resource_type: str, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"{resource_type}\0{encoded}".encode()).hexdigest()

    @staticmethod
    def _required_string(payload: dict[str, Any], field: str, context: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise BrandAnalyticsMalformedResponseError(
                f"Amazon Brand Analytics {context} did not contain {field}."
            )
        return value

    @staticmethod
    def _json_object(response: httpx.Response, context: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BrandAnalyticsMalformedResponseError(f"{context} was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise BrandAnalyticsMalformedResponseError(f"{context} was not a JSON object.")
        return payload

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
