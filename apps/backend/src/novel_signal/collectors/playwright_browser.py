"""Safe Playwright foundation for public, logged-out page collection.

This module captures one allowlisted page at a time. It does not persist raw
evidence, parse HTML, automate accounts, or attempt to bypass access controls.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


class BrowserDeviceType(StrEnum):
    DESKTOP = "desktop"
    MOBILE = "mobile"


class ChallengeKind(StrEnum):
    NONE = "none"
    CAPTCHA = "captcha"
    LOGIN_WALL = "login_wall"
    BOT_CHALLENGE = "bot_challenge"


class PlaywrightBrowserError(RuntimeError):
    """Base error for safe browser-collector failures."""


class BrowserConfigurationError(PlaywrightBrowserError):
    """The browser profile or lifecycle configuration is invalid."""


class UnsupportedTargetError(PlaywrightBrowserError):
    """A target URL or page type falls outside the explicit policy."""


class BrowserNavigationTimeoutError(PlaywrightBrowserError):
    """The public page did not finish navigation within the configured bound."""


class BrowserNavigationError(PlaywrightBrowserError):
    """The public page could not be navigated safely."""


class BrowserLifecycleError(PlaywrightBrowserError):
    """Playwright or Chromium could not be started or shut down safely."""


class ChallengeDetectedError(PlaywrightBrowserError):
    """Reserved for later callers that convert a capture challenge into a failure."""


@dataclass(frozen=True)
class BrowserViewport:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise BrowserConfigurationError("Viewport dimensions must be positive.")


@dataclass(frozen=True)
class BrowserGeolocation:
    latitude: float
    longitude: float
    accuracy: float | None = None

    def as_context_option(self) -> dict[str, float]:
        result = {"latitude": self.latitude, "longitude": self.longitude}
        if self.accuracy is not None:
            result["accuracy"] = self.accuracy
        return result


@dataclass(frozen=True)
class BrowserProfile:
    """An isolated normal-device browser context configuration."""

    profile_id: str
    device_type: BrowserDeviceType = BrowserDeviceType.DESKTOP
    viewport: BrowserViewport = BrowserViewport(width=1440, height=900)
    user_agent: str | None = None
    locale: str = "en-IN"
    timezone_id: str = "Asia/Kolkata"
    country_code: str = "IN"
    geolocation: BrowserGeolocation | None = None
    pincode: str | None = None
    location_label: str | None = None

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise BrowserConfigurationError("Browser profile identifier is required.")
        if not self.locale.strip() or not self.timezone_id.strip() or not self.country_code.strip():
            raise BrowserConfigurationError("Locale, timezone, and country are required.")
        if self.user_agent is not None and not self.user_agent.strip():
            raise BrowserConfigurationError("User agent must be non-blank when configured.")

    def context_options(self) -> dict[str, Any]:
        """Return normal Playwright context options without stealth modifications."""
        options: dict[str, Any] = {
            "viewport": {"width": self.viewport.width, "height": self.viewport.height},
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "is_mobile": self.device_type is BrowserDeviceType.MOBILE,
            "has_touch": self.device_type is BrowserDeviceType.MOBILE,
        }
        if self.user_agent is not None:
            options["user_agent"] = self.user_agent
        if self.geolocation is not None:
            options["geolocation"] = self.geolocation.as_context_option()
            options["permissions"] = ["geolocation"]
        return options


@dataclass(frozen=True)
class BrowserTargetPolicy:
    """Explicit hostname and page-type allowlisting for public capture targets."""

    allowed_domains: frozenset[str]
    allowed_page_types: frozenset[str]

    def __post_init__(self) -> None:
        domains = frozenset(_normalize_allowed_domain(domain) for domain in self.allowed_domains)
        page_types = frozenset(page_type.strip() for page_type in self.allowed_page_types)
        if not domains or not page_types or any(not page_type for page_type in page_types):
            raise BrowserConfigurationError("Target policy needs domains and page types.")
        object.__setattr__(self, "allowed_domains", domains)
        object.__setattr__(self, "allowed_page_types", page_types)

    def validate(self, *, url: str, page_type: str) -> None:
        if page_type not in self.allowed_page_types:
            raise UnsupportedTargetError("Page type is not allowed for browser capture.")
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or not _is_valid_hostname(hostname)
        ):
            raise UnsupportedTargetError("Target URL is not a supported public HTTP URL.")
        normalized_hostname = hostname.rstrip(".").lower()
        if _is_internal_hostname(normalized_hostname):
            raise UnsupportedTargetError("Internal target hostnames are not supported.")
        if not any(
            normalized_hostname == domain or normalized_hostname.endswith(f".{domain}")
            for domain in self.allowed_domains
        ):
            raise UnsupportedTargetError("Target hostname is not allowlisted for browser capture.")


@dataclass(frozen=True)
class BrowserCaptureRequest:
    requested_url: str
    page_type: str
    profile: BrowserProfile
    capture_screenshot: bool = False


@dataclass(frozen=True)
class ChallengeState:
    kind: ChallengeKind = ChallengeKind.NONE
    reason_code: str | None = None

    @property
    def detected(self) -> bool:
        return self.kind is not ChallengeKind.NONE


@dataclass(frozen=True)
class BrowserCaptureResult:
    requested_url: str
    final_url: str
    status: int | None
    html: bytes
    content_type: str
    captured_at: datetime
    page_type: str
    profile_id: str
    challenge: ChallengeState
    screenshot: bytes | None = None

    @property
    def challenge_detected(self) -> bool:
        return self.challenge.detected


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class PlaywrightBrowserSession:
    """A bounded browser lifecycle with one isolated context per profile.

    Contexts exist only in memory for the lifetime of this session. They are never
    persistent contexts and therefore do not retain cookies or account state on disk.
    """

    def __init__(
        self,
        *,
        policy: BrowserTargetPolicy,
        max_concurrency: int = 1,
        min_delay_seconds: float = 1.0,
        navigation_timeout_seconds: float = 45.0,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        if max_concurrency < 1:
            raise BrowserConfigurationError("Browser concurrency must be at least one.")
        if min_delay_seconds < 0 or navigation_timeout_seconds <= 0:
            raise BrowserConfigurationError("Browser delay and timeout values are invalid.")
        self.policy = policy
        self.max_concurrency = max_concurrency
        self.min_delay_seconds = min_delay_seconds
        self.navigation_timeout_ms = int(navigation_timeout_seconds * 1000)
        self._sleep = sleep
        self._clock = clock
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._pacing_lock = asyncio.Lock()
        self._next_navigation_at = 0.0
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, tuple[BrowserProfile, BrowserContext]] = {}

    @property
    def is_started(self) -> bool:
        return self._browser is not None

    @property
    def active_context_count(self) -> int:
        return len(self._contexts)

    async def __aenter__(self) -> PlaywrightBrowserSession:
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._browser is not None:
            return
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        except Exception:
            await self._close_handles()
            raise BrowserLifecycleError("Browser collector could not start safely.") from None

    async def close(self) -> None:
        await self._close_handles()

    async def capture(self, request: BrowserCaptureRequest) -> BrowserCaptureResult:
        self.policy.validate(url=request.requested_url, page_type=request.page_type)
        browser = self._browser
        if browser is None:
            raise BrowserLifecycleError("Browser collector session has not been started.")

        async with self._semaphore:
            await self._wait_for_pacing()
            context = await self._context_for(request.profile)
            page: Page | None = None
            try:
                page = await context.new_page()
                response = await page.goto(
                    request.requested_url,
                    wait_until="domcontentloaded",
                    timeout=self.navigation_timeout_ms,
                )
                if response is None:
                    raise BrowserNavigationError("Browser navigation did not return a response.")
                self.policy.validate(url=page.url, page_type=request.page_type)
                result = await self._capture_response(page, response, request)
                if result.challenge_detected:
                    await self._discard_context(request.profile.profile_id)
                return result
            except PlaywrightTimeoutError:
                await self._discard_context(request.profile.profile_id)
                raise BrowserNavigationTimeoutError("Browser navigation timed out.") from None
            except PlaywrightBrowserError:
                await self._discard_context(request.profile.profile_id)
                raise
            except asyncio.CancelledError:
                await self._discard_context(request.profile.profile_id)
                raise
            except PlaywrightError:
                await self._discard_context(request.profile.profile_id)
                raise BrowserNavigationError("Browser navigation failed.") from None
            except Exception:
                await self._discard_context(request.profile.profile_id)
                raise BrowserNavigationError("Browser capture failed.") from None
            finally:
                if page is not None:
                    with contextlib.suppress(Exception):
                        await page.close()

    async def _capture_response(
        self,
        page: Page,
        response: Response,
        request: BrowserCaptureRequest,
    ) -> BrowserCaptureResult:
        html = await response.body()
        content_type = response.headers.get("content-type", "application/octet-stream")
        title = await page.title()
        visible_text = await page.locator("body").inner_text(timeout=self.navigation_timeout_ms)
        challenge = detect_challenge(final_url=page.url, title=title, visible_text=visible_text)
        screenshot = await page.screenshot() if request.capture_screenshot else None
        return BrowserCaptureResult(
            requested_url=request.requested_url,
            final_url=page.url,
            status=response.status,
            html=html,
            content_type=content_type,
            captured_at=datetime.now(UTC),
            page_type=request.page_type,
            profile_id=request.profile.profile_id,
            challenge=challenge,
            screenshot=screenshot,
        )

    async def _context_for(self, profile: BrowserProfile) -> BrowserContext:
        current = self._contexts.get(profile.profile_id)
        if current is not None:
            configured_profile, context = current
            if configured_profile != profile:
                raise BrowserConfigurationError(
                    "Browser profile identifier has conflicting settings."
                )
            return context
        browser = self._browser
        if browser is None:
            raise BrowserLifecycleError("Browser collector session has not been started.")
        try:
            context = await browser.new_context(**profile.context_options())
        except PlaywrightError:
            raise BrowserLifecycleError("Browser context could not be created safely.") from None
        self._contexts[profile.profile_id] = (profile, context)
        return context

    async def _discard_context(self, profile_id: str) -> None:
        current = self._contexts.pop(profile_id, None)
        if current is not None:
            with contextlib.suppress(Exception):
                await current[1].close()

    async def _wait_for_pacing(self) -> None:
        async with self._pacing_lock:
            now = self._clock()
            wait_seconds = max(0.0, self._next_navigation_at - now)
            self._next_navigation_at = max(now, self._next_navigation_at) + self.min_delay_seconds
        if wait_seconds > 0:
            await self._sleep(wait_seconds)

    async def _close_handles(self) -> None:
        contexts = tuple(self._contexts.values())
        self._contexts.clear()
        for _, context in contexts:
            with contextlib.suppress(Exception):
                await context.close()
        browser, self._browser = self._browser, None
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        playwright, self._playwright = self._playwright, None
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()


def detect_challenge(*, final_url: str, title: str, visible_text: str) -> ChallengeState:
    """Classify common public blockers using intentionally conservative page signals."""
    url = final_url.lower()
    title_and_text = f"{title}\n{visible_text}".lower()
    if any(signal in title_and_text for signal in _CAPTCHA_SIGNALS):
        return ChallengeState(ChallengeKind.CAPTCHA, "captcha_signal")
    if any(signal in url for signal in ("/signin", "/login", "/ap/signin")) or any(
        signal in title_and_text for signal in _LOGIN_SIGNALS
    ):
        return ChallengeState(ChallengeKind.LOGIN_WALL, "login_wall_signal")
    if any(signal in title_and_text for signal in _BOT_SIGNALS):
        return ChallengeState(ChallengeKind.BOT_CHALLENGE, "bot_challenge_signal")
    return ChallengeState()


_CAPTCHA_SIGNALS = (
    "verify you are human",
    "captcha",
    "enter the characters you see below",
)
_LOGIN_SIGNALS = (
    "sign in to continue",
    "please sign in",
    "login required",
)
_BOT_SIGNALS = (
    "access denied",
    "automated access",
    "unusual traffic",
    "suspicious automated request",
    "temporarily blocked",
)


def _normalize_allowed_domain(domain: str) -> str:
    normalized = domain.strip().rstrip(".").lower()
    if not normalized or "/" in normalized or not _is_valid_hostname(normalized):
        raise BrowserConfigurationError("Allowed domain is invalid.")
    return normalized


def _is_valid_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".")
    if not normalized or len(normalized) > 253:
        return False
    labels = normalized.split(".")
    return all(
        label
        and len(label) <= 63
        and not label.startswith("-")
        and not label.endswith("-")
        and all(character.isalnum() or character == "-" for character in label)
        for label in labels
    )


def _is_internal_hostname(hostname: str) -> bool:
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return not address.is_global
