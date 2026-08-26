from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from urllib.parse import quote_plus, urlparse

import httpx

from novel_signal.collectors.base import CaptureRequest, CaptureResult


class AmazonChallengeError(RuntimeError):
    """Amazon asked for a challenge or authentication; the caller must stop."""


class AmazonPublicCollector:
    """Conservative, logged-out collector for allow-listed Amazon.in pages."""

    _challenge_markers = (
        "captcha",
        "robot check",
        "enter the characters you see below",
        "automated access",
        "sorry! something went wrong",
    )

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 45,
        min_delay_seconds: float = 8,
        max_delay_seconds: float = 15,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_source: random.Random | None = None,
    ) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.sleep = sleep
        self.random = random_source or random.SystemRandom()
        self._last_request_at: float | None = None

    @staticmethod
    def search_url(keyword: str) -> str:
        value = keyword.strip()
        if not value:
            raise ValueError("keyword must not be blank")
        return f"https://www.amazon.in/s?k={quote_plus(value)}"

    @staticmethod
    def product_url(asin: str) -> str:
        value = asin.strip().upper()
        if not value:
            raise ValueError("ASIN must not be blank")
        return f"https://www.amazon.in/dp/{quote_plus(value)}"

    async def capture(self, request: CaptureRequest) -> CaptureResult:
        parsed = urlparse(request.url)
        if parsed.scheme != "https" or parsed.hostname not in {"amazon.in", "www.amazon.in"}:
            raise ValueError("Amazon public collector only accepts https://www.amazon.in URLs")
        await self._throttle()
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=True,
            headers={
                "Accept-Language": "en-IN,en;q=0.9",
                "User-Agent": "NovelSignal/0.1 (public Amazon research; contact admin)",
            },
        )
        try:
            response = await client.get(request.url)
        except httpx.TimeoutException as error:
            raise TimeoutError("Amazon public page request timed out") from error
        except httpx.HTTPError as error:
            raise ConnectionError("Amazon public page request failed") from error
        finally:
            if owns_client:
                await client.aclose()

        body = response.content
        text = body.decode("utf-8", errors="ignore").lower()
        challenge = response.status_code in {403, 429} or any(
            marker in text for marker in self._challenge_markers
        )
        if challenge:
            raise AmazonChallengeError(
                "Amazon challenge detected; raw capture must be retained and this attempt stopped"
            )
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Amazon returned HTTP {response.status_code}",
                request=response.request,
                response=response,
            )
        return CaptureResult(
            final_url=str(response.url),
            body=body,
            content_type=response.headers.get("content-type", "text/html"),
        )

    async def _throttle(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = asyncio.get_running_loop().time()
            return
        now = asyncio.get_running_loop().time()
        delay = self.random.uniform(self.min_delay_seconds, self.max_delay_seconds)
        remaining = delay - (now - self._last_request_at)
        if remaining > 0:
            await self.sleep(remaining)
        self._last_request_at = asyncio.get_running_loop().time()
