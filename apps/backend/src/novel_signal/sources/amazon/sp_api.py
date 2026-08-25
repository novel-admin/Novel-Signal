"""Amazon Selling Partner API connection verification boundary.

This adapter deliberately proves credentials and marketplace access only. Collection,
normalization, persistence, and scheduling remain outside this Week 2 readiness slice.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from botocore.auth import SigV4Auth  # type: ignore[import-untyped]
from botocore.awsrequest import AWSRequest  # type: ignore[import-untyped]
from botocore.credentials import Credentials  # type: ignore[import-untyped]

from novel_signal.config import Settings, get_settings
from novel_signal.sources.base import RawSourcePage, SourceType, SyncRequest

SOURCE_TYPE = SourceType.AMAZON_SP_API
_LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
_MARKETPLACE_PARTICIPATIONS_PATH = "/sellers/v1/marketplaceParticipations"
_CATALOG_ITEMS_RESOURCE = "catalog_items"
_PRICING_OFFERS_RESOURCE = "pricing_offers"
_INVENTORY_SUMMARIES_RESOURCE = "inventory_summaries"


class AmazonSpApiError(RuntimeError):
    """Base error raised by the Amazon Selling Partner API adapter."""


class AmazonSpApiConfigurationError(AmazonSpApiError):
    """Required connection settings are absent."""


class AmazonSpApiAuthenticationError(AmazonSpApiError):
    """LWA or SP-API rejected the supplied credentials."""


class AmazonSpApiPermissionError(AmazonSpApiError):
    """Credentials are valid but cannot access the configured marketplace."""


class AmazonSpApiRateLimitError(AmazonSpApiError):
    """Amazon asked the caller to retry later."""

    def __init__(self, retry_after: str | None) -> None:
        self.retry_after = retry_after
        delay = retry_after or "an unspecified delay"
        super().__init__(f"Amazon SP-API rate limit; retry after {delay}.")


class AmazonSpApiMalformedResponseError(AmazonSpApiError):
    """Amazon returned a response that cannot prove the requested access."""


class AmazonSpApiNetworkError(AmazonSpApiError):
    """The connection verification request could not reach Amazon."""


class AmazonSpApiUnsupportedOperationError(AmazonSpApiError):
    """The requested operation is intentionally outside the verification-only slice."""


class AmazonSpApiUnsupportedResourceError(AmazonSpApiError):
    """The requested raw resource is not part of the current adapter scope."""


class AmazonSpApiCursorError(AmazonSpApiError):
    """A raw-fetch cursor lacks the target identity required by its resource."""


@dataclass(frozen=True)
class AmazonSpApiConfig:
    """Connection settings required to verify Selling Partner API access."""

    lwa_client_id: str = field(repr=False)
    lwa_client_secret: str = field(repr=False)
    lwa_refresh_token: str = field(repr=False)
    aws_access_key_id: str = field(repr=False)
    aws_secret_access_key: str = field(repr=False)
    marketplace_id: str = "A21TJRUUN4KGV"
    region: str = "eu-west-1"
    role_arn: str = ""
    api_base_url: str = "https://sellingpartnerapi-eu.amazon.com"
    token_url: str = _LWA_TOKEN_URL

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> AmazonSpApiConfig:
        current = settings or get_settings()
        return cls(
            lwa_client_id=current.amazon_lwa_client_id,
            lwa_client_secret=current.amazon_lwa_client_secret.get_secret_value(),
            lwa_refresh_token=current.amazon_lwa_refresh_token.get_secret_value(),
            aws_access_key_id=current.amazon_aws_access_key_id,
            aws_secret_access_key=current.amazon_aws_secret_access_key.get_secret_value(),
            marketplace_id=current.amazon_marketplace_id,
            region=current.amazon_region,
            role_arn=current.amazon_role_arn,
            api_base_url=_sp_api_base_url_for_region(current.amazon_region),
        )

    def validate(self) -> None:
        missing = tuple(
            name
            for name, value in (
                ("amazon_lwa_client_id", self.lwa_client_id),
                ("amazon_lwa_client_secret", self.lwa_client_secret),
                ("amazon_lwa_refresh_token", self.lwa_refresh_token),
                ("amazon_aws_access_key_id", self.aws_access_key_id),
                ("amazon_aws_secret_access_key", self.aws_secret_access_key),
                ("amazon_region", self.region),
                ("amazon_marketplace_id", self.marketplace_id),
            )
            if not value.strip()
        )
        if missing:
            raise AmazonSpApiConfigurationError(
                f"Amazon SP-API configuration is missing: {', '.join(missing)}."
            )


def _sp_api_base_url_for_region(region: str) -> str:
    if region.startswith("eu-"):
        return "https://sellingpartnerapi-eu.amazon.com"
    if region.startswith(("us-", "ca-", "mx-", "br-")):
        return "https://sellingpartnerapi-na.amazon.com"
    return "https://sellingpartnerapi-fe.amazon.com"


class AmazonSpApiClient:
    """Verifies Amazon SP-API credentials with a signed marketplace access request."""

    source_type = SOURCE_TYPE

    def __init__(
        self,
        config: AmazonSpApiConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.config = config
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)
        self._access_token: str | None = None

    async def __aenter__(self) -> AmazonSpApiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    async def verify_connection(self) -> None:
        """Prove that LWA, SigV4 signing, and configured marketplace access work."""
        self.config.validate()
        access_token = await self._lwa_access_token()
        response = await self._marketplace_participations(access_token)
        self._validate_marketplace_access(response)

    async def fetch(self, request: SyncRequest) -> tuple[RawSourcePage, ...]:
        """Fetch raw owned-product pages without parsing or persisting their contents.

        ``request.cursor`` carries the target identity because :class:`SyncRequest`
        intentionally has no product-target field. Catalog and offer requests require
        ``{"asin": "..."}``; inventory requests require ``{"seller_sku": "..."}``
        and use ``next_token`` only for continuation.
        """
        cursor = self._parse_cursor(request.resource_type, request.cursor)
        pages: list[RawSourcePage] = []
        while True:
            path, params = self._resource_request(request.resource_type, cursor)
            response, request_url = await self._authenticated_get(path, params)
            body = response.content
            next_cursor = self._next_cursor(request.resource_type, cursor, body)
            pages.append(
                RawSourcePage(
                    source=SOURCE_TYPE,
                    resource_type=request.resource_type,
                    body=body,
                    content_type=response.headers.get("content-type", "application/json"),
                    request_fingerprint=self._fingerprint(request.resource_type, request_url),
                    next_cursor=next_cursor,
                )
            )
            if next_cursor is None:
                return tuple(pages)
            cursor = next_cursor

    async def _lwa_access_token(self) -> str:
        if self._access_token is not None:
            return self._access_token
        try:
            response = await self._client.post(
                self.config.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.lwa_refresh_token,
                    "client_id": self.config.lwa_client_id,
                    "client_secret": self.config.lwa_client_secret,
                },
            )
        except httpx.TimeoutException as exc:
            raise AmazonSpApiNetworkError("Amazon LWA token request timed out.") from exc
        except httpx.RequestError as exc:
            raise AmazonSpApiNetworkError("Amazon LWA token request failed.") from exc

        if response.status_code in (401, 403):
            raise AmazonSpApiAuthenticationError("Amazon LWA credentials were rejected.")
        if response.status_code == 429:
            raise AmazonSpApiRateLimitError(response.headers.get("Retry-After"))
        if response.is_error:
            raise AmazonSpApiError(
                f"Amazon LWA token request failed with status {response.status_code}."
            )
        payload = self._json_object(response, "Amazon LWA token response")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise AmazonSpApiMalformedResponseError(
                "Amazon LWA token response did not contain an access token."
            )
        self._access_token = token
        return token

    async def _marketplace_participations(self, access_token: str) -> httpx.Response:
        response, _ = await self._authenticated_get(
            _MARKETPLACE_PARTICIPATIONS_PATH, {}, access_token=access_token
        )
        return response

    async def _authenticated_get(
        self,
        path: str,
        params: dict[str, str],
        *,
        access_token: str | None = None,
    ) -> tuple[httpx.Response, str]:
        token = access_token or await self.get_access_token()
        url = str(httpx.URL(f"{self.config.api_base_url.rstrip('/')}{path}", params=params))
        signed_headers = self.signed_headers("GET", url, token)
        try:
            response = await self._client.get(url, headers=signed_headers)
        except httpx.TimeoutException as exc:
            raise AmazonSpApiNetworkError("Amazon SP-API request timed out.") from exc
        except httpx.RequestError as exc:
            raise AmazonSpApiNetworkError("Amazon SP-API request failed.") from exc

        if response.status_code == 401:
            raise AmazonSpApiAuthenticationError("Amazon SP-API credentials were rejected.")
        if response.status_code == 403:
            raise AmazonSpApiPermissionError("Amazon SP-API access was denied.")
        if response.status_code == 429:
            raise AmazonSpApiRateLimitError(response.headers.get("Retry-After"))
        if response.is_error:
            raise AmazonSpApiError(
                f"Amazon SP-API request failed with status {response.status_code}."
            )
        return response, url

    async def get_access_token(self) -> str:
        """Return a cached LWA token for a separately scoped SP-API request."""
        self.config.validate()
        return await self._lwa_access_token()

    def signed_headers(self, method: str, url: str, access_token: str) -> dict[str, str]:
        """Create SigV4 headers without sending a request or retaining credentials."""
        request = AWSRequest(
            method=method,
            url=url,
            headers={"x-amz-access-token": access_token},
        )
        credentials = Credentials(
            self.config.aws_access_key_id,
            self.config.aws_secret_access_key,
        )
        SigV4Auth(credentials, "execute-api", self.config.region).add_auth(request)
        return {str(key): str(value) for key, value in request.headers.items()}

    def _parse_cursor(self, resource_type: str, cursor: dict[str, Any] | None) -> dict[str, str]:
        if resource_type not in {
            _CATALOG_ITEMS_RESOURCE,
            _PRICING_OFFERS_RESOURCE,
            _INVENTORY_SUMMARIES_RESOURCE,
        }:
            raise AmazonSpApiUnsupportedResourceError(
                f"Unsupported Amazon SP-API resource: {resource_type}."
            )
        if not isinstance(cursor, dict):
            raise AmazonSpApiCursorError("Amazon SP-API raw fetch requires a cursor object.")
        target_key = "seller_sku" if resource_type == _INVENTORY_SUMMARIES_RESOURCE else "asin"
        target = cursor.get(target_key)
        if not isinstance(target, str) or not target.strip():
            raise AmazonSpApiCursorError(
                f"Amazon SP-API {resource_type} cursor requires a non-empty {target_key}."
            )
        next_token = cursor.get("next_token")
        if next_token is not None and (not isinstance(next_token, str) or not next_token.strip()):
            raise AmazonSpApiCursorError(
                "Amazon SP-API cursor next_token must be a non-empty string."
            )
        parsed = {target_key: target}
        if isinstance(next_token, str):
            parsed["next_token"] = next_token
        return parsed

    def _resource_request(
        self, resource_type: str, cursor: dict[str, str]
    ) -> tuple[str, dict[str, str]]:
        if resource_type == _CATALOG_ITEMS_RESOURCE:
            return (
                f"/catalog/2022-04-01/items/{cursor['asin']}",
                {
                    "marketplaceIds": self.config.marketplace_id,
                    "includedData": "attributes,images,productTypes,summaries",
                },
            )
        if resource_type == _PRICING_OFFERS_RESOURCE:
            return (
                f"/products/pricing/v0/items/{cursor['asin']}/offers",
                {"MarketplaceId": self.config.marketplace_id, "ItemCondition": "New"},
            )
        params = {
            "granularityType": "Marketplace",
            "granularityId": self.config.marketplace_id,
            "marketplaceIds": self.config.marketplace_id,
            "details": "true",
            "sellerSkus": cursor["seller_sku"],
        }
        if "next_token" in cursor:
            params["nextToken"] = cursor["next_token"]
        return "/fba/inventory/v1/summaries", params

    def _next_cursor(
        self, resource_type: str, cursor: dict[str, str], body: bytes
    ) -> dict[str, str] | None:
        if resource_type != _INVENTORY_SUMMARIES_RESOURCE or not body:
            return None
        payload = self._json_object_from_bytes(body, "Amazon SP-API inventory response")
        pagination = payload.get("pagination")
        if pagination is None:
            return None
        if not isinstance(pagination, dict):
            raise AmazonSpApiMalformedResponseError(
                "Amazon SP-API inventory response contained invalid pagination metadata."
            )
        next_token = pagination.get("nextToken")
        if next_token is None:
            return None
        if not isinstance(next_token, str) or not next_token.strip():
            raise AmazonSpApiMalformedResponseError(
                "Amazon SP-API inventory response contained an invalid next token."
            )
        return {"seller_sku": cursor["seller_sku"], "next_token": next_token}

    @staticmethod
    def _fingerprint(resource_type: str, request_url: str) -> str:
        digest = hashlib.sha256()
        digest.update(resource_type.encode())
        digest.update(b"\0")
        digest.update(request_url.encode())
        return digest.hexdigest()

    @staticmethod
    def _json_object_from_bytes(body: bytes, context: str) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AmazonSpApiMalformedResponseError(f"{context} was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise AmazonSpApiMalformedResponseError(f"{context} was not a JSON object.")
        return payload

    def _validate_marketplace_access(self, response: httpx.Response) -> None:
        payload = self._json_object(response, "Amazon SP-API marketplace response")
        participations = payload.get("payload")
        if not isinstance(participations, list):
            raise AmazonSpApiMalformedResponseError(
                "Amazon SP-API marketplace response did not contain a participation list."
            )
        marketplace_ids = {
            marketplace.get("id")
            for participation in participations
            if isinstance(participation, dict)
            and isinstance(marketplace := participation.get("marketplace"), dict)
            and isinstance(marketplace.get("id"), str)
        }
        if self.config.marketplace_id not in marketplace_ids:
            raise AmazonSpApiPermissionError(
                "Configured Amazon marketplace is unavailable to this seller."
            )

    @staticmethod
    def _json_object(response: httpx.Response, context: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise AmazonSpApiMalformedResponseError(f"{context} was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise AmazonSpApiMalformedResponseError(f"{context} was not a JSON object.")
        return payload
