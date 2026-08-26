"""Raw-first Google Ads API client for Novel-owned advertising accounts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx

from novel_signal.config import Settings, get_settings
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.GOOGLE_ADS_API
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE_URL = "https://googleads.googleapis.com/v18"


class GoogleAdsError(RuntimeError):
    """Base error for the Google Ads boundary."""


class GoogleAdsConfigurationError(GoogleAdsError):
    pass


class GoogleAdsPermissionError(GoogleAdsError):
    pass


class GoogleAdsRateLimitError(GoogleAdsError):
    pass


class GoogleAdsMalformedResponseError(GoogleAdsError):
    pass


@dataclass(frozen=True)
class GoogleAdsConfig:
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    customer_id: str
    login_customer_id: str = ""
    api_base_url: str = API_BASE_URL
    token_url: str = TOKEN_URL

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> GoogleAdsConfig:
        current = settings or get_settings()
        return cls(
            developer_token=current.google_ads_developer_token.get_secret_value(),
            client_id=current.google_ads_client_id,
            client_secret=current.google_ads_client_secret.get_secret_value(),
            refresh_token=current.google_ads_refresh_token.get_secret_value(),
            customer_id=current.google_ads_customer_id.replace("-", ""),
            login_customer_id=current.google_ads_login_customer_id.replace("-", ""),
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("google_ads_developer_token", self.developer_token),
                ("google_ads_client_id", self.client_id),
                ("google_ads_client_secret", self.client_secret),
                ("google_ads_refresh_token", self.refresh_token),
                ("google_ads_customer_id", self.customer_id),
            )
            if not value.strip()
        ]
        if missing:
            raise GoogleAdsConfigurationError(
                f"Google Ads configuration is missing: {', '.join(missing)}"
            )


class GoogleAdsClient:
    source_type = SOURCE_TYPE

    def __init__(
        self, config: GoogleAdsConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(transport=transport, timeout=45.0)
        self._access_token: str | None = None

    async def __aenter__(self) -> GoogleAdsClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def verify_connection(self) -> None:
        self.config.validate()
        pages = await self._search(
            "SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1"
        )
        if not pages:
            raise GoogleAdsMalformedResponseError("Google Ads verification returned no response")

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        self.config.validate()
        query = self._query_for(
            request.resource_type,
            request.window_start.date().isoformat(),
            request.window_end.date().isoformat(),
        )
        return await self._search(query, resource_type=request.resource_type)

    async def _token(self) -> str:
        if self._access_token:
            return self._access_token
        response = await self._client.post(
            self.config.token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "refresh_token": self.config.refresh_token,
            },
        )
        self._raise_for_status(response, "OAuth token")
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise GoogleAdsMalformedResponseError(
                "Google OAuth response did not contain access_token"
            )
        self._access_token = token
        return token

    async def _search(
        self, query: str, *, resource_type: str = "verification"
    ) -> tuple[RawSourcePage, ...]:
        token = await self._token()
        headers = {
            "Authorization": f"Bearer {token}",
            "developer-token": self.config.developer_token,
            "Content-Type": "application/json",
        }
        if self.config.login_customer_id:
            headers["login-customer-id"] = self.config.login_customer_id
        response = await self._client.post(
            f"{self.config.api_base_url}/customers/{self.config.customer_id}/googleAds:searchStream",
            headers=headers,
            json={"query": query},
        )
        self._raise_for_status(response, "Google Ads search")
        body = response.content
        return (
            RawSourcePage(
                source=SOURCE_TYPE,
                resource_type=resource_type,
                body=body,
                content_type=response.headers.get("content-type", "application/json"),
                request_fingerprint=hashlib.sha256(
                    f"{self.config.customer_id}:{resource_type}:{query}".encode()
                ).hexdigest(),
            ),
        )

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        if response.status_code in (401, 403):
            raise GoogleAdsPermissionError(f"{context} permission denied")
        if response.status_code == 429:
            raise GoogleAdsRateLimitError(f"{context} rate limited")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise GoogleAdsError(f"{context} failed with status {response.status_code}") from error

    @staticmethod
    def _query_for(resource_type: str, start_date: str, end_date: str) -> str:
        metrics = (
            "metrics.impressions, metrics.clicks, metrics.cost_micros, "
            "metrics.conversions, metrics.conversions_value"
        )
        resources = {
            "campaigns": f"campaign.id, campaign.name, campaign.status, {metrics}",
            "ad_groups": f"ad_group.id, ad_group.name, ad_group.status, {metrics}",
            "search_terms": (
                "search_term_view.search_term, campaign.id, ad_group.id, " + metrics
            ),
            "keywords": (
                "ad_group_criterion.criterion_id, ad_group_criterion.keyword.text, "
                "ad_group_criterion.status, " + metrics
            ),
        }
        fields = resources.get(resource_type)
        if fields is None:
            raise GoogleAdsConfigurationError(f"Unsupported Google Ads resource: {resource_type}")
        roots = {
            "campaigns": "campaign",
            "ad_groups": "ad_group",
            "search_terms": "search_term_view",
            "keywords": "keyword_view",
        }
        root = roots[resource_type]
        return (
            f"SELECT {fields} FROM {root} "
            f"WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'"
        )
