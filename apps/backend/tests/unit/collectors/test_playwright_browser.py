from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC
from typing import Any

import pytest
from novel_signal.collectors.playwright_browser import (
    BrowserCaptureRequest,
    BrowserConfigurationError,
    BrowserDeviceType,
    BrowserGeolocation,
    BrowserNavigationError,
    BrowserNavigationTimeoutError,
    BrowserProfile,
    BrowserTargetPolicy,
    BrowserViewport,
    ChallengeKind,
    PlaywrightBrowserSession,
    UnsupportedTargetError,
    detect_challenge,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


@dataclass
class FakeResponse:
    body_bytes: bytes = b"<html><title>Public page</title><body>Normal content</body></html>"
    status: int = 200
    content_type: str = "text/html; charset=utf-8"

    @property
    def headers(self) -> dict[str, str]:
        return {"content-type": self.content_type}

    async def body(self) -> bytes:
        return self.body_bytes


class FakeLocator:
    def __init__(self, text: str) -> None:
        self.text = text

    async def inner_text(self, *, timeout: float) -> str:
        del timeout
        return self.text


class FakePage:
    def __init__(
        self,
        *,
        response: FakeResponse | None = None,
        final_url: str = "https://www.amazon.in/final",
        title: str = "Public page",
        visible_text: str = "Normal public content",
        error: Exception | None = None,
        block: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
        activity: dict[str, int] | None = None,
    ) -> None:
        self.response = response or FakeResponse()
        self.url = final_url
        self.title_text = title
        self.visible_text = visible_text
        self.error = error
        self.block = block
        self.release = release
        self.activity = activity
        self.closed = False
        self.goto_calls = 0

    async def goto(self, url: str, **_: Any) -> FakeResponse | None:
        del url
        self.goto_calls += 1
        if self.error is not None:
            raise self.error
        if self.block is not None and self.release is not None and self.activity is not None:
            self.activity["active"] += 1
            self.activity["maximum"] = max(self.activity["maximum"], self.activity["active"])
            self.block.set()
            await self.release.wait()
            self.activity["active"] -= 1
        return self.response

    async def title(self) -> str:
        return self.title_text

    def locator(self, selector: str) -> FakeLocator:
        assert selector == "body"
        return FakeLocator(self.visible_text)

    async def screenshot(self) -> bytes:
        return b"\x89PNG\r\nfixture"

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages
        self.closed = False

    async def new_page(self) -> FakePage:
        return self.pages.pop(0)

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages
        self.context_options: list[dict[str, Any]] = []
        self.contexts: list[FakeContext] = []
        self.closed = False

    async def new_context(self, **options: Any) -> FakeContext:
        self.context_options.append(options)
        context = FakeContext(self.pages)
        self.contexts.append(context)
        return context

    async def close(self) -> None:
        self.closed = True


def policy() -> BrowserTargetPolicy:
    return BrowserTargetPolicy(
        allowed_domains=frozenset({"amazon.in", "google.com"}),
        allowed_page_types=frozenset({"amazon_serp", "google_serp"}),
    )


def profile(*, device_type: BrowserDeviceType = BrowserDeviceType.DESKTOP) -> BrowserProfile:
    return BrowserProfile(profile_id="in-desktop", device_type=device_type)


def session_with_pages(
    pages: list[FakePage],
    *,
    max_concurrency: int = 1,
    min_delay_seconds: float = 0,
    sleep: Any = asyncio.sleep,
    clock: Any = time.monotonic,
) -> tuple[PlaywrightBrowserSession, FakeBrowser]:
    session = PlaywrightBrowserSession(
        policy=policy(),
        max_concurrency=max_concurrency,
        min_delay_seconds=min_delay_seconds,
        sleep=sleep,
        clock=clock,
    )
    browser = FakeBrowser(pages)
    session._browser = browser  # type: ignore[assignment]
    return session, browser


def request(*, url: str = "https://www.amazon.in/s?k=diapers") -> BrowserCaptureRequest:
    return BrowserCaptureRequest(requested_url=url, page_type="amazon_serp", profile=profile())


def test_target_policy_accepts_hostname_and_rejects_confusable_hosts() -> None:
    target_policy = policy()

    target_policy.validate(url="https://www.amazon.in/s?k=diapers", page_type="amazon_serp")
    target_policy.validate(url="https://smile.amazon.in/s?k=diapers", page_type="amazon_serp")

    with pytest.raises(UnsupportedTargetError):
        target_policy.validate(
            url="https://amazon.in.evil.example/s?k=diapers", page_type="amazon_serp"
        )
    with pytest.raises(UnsupportedTargetError):
        target_policy.validate(url="mailto:public@example.com", page_type="amazon_serp")
    with pytest.raises(UnsupportedTargetError):
        target_policy.validate(url="https://www.amazon.in/", page_type="product_page")


@pytest.mark.asyncio
async def test_profile_context_options_cover_desktop_mobile_and_geo() -> None:
    desktop = profile().context_options()
    assert desktop["viewport"] == {"width": 1440, "height": 900}
    assert desktop["is_mobile"] is False
    assert desktop["has_touch"] is False

    mobile = BrowserProfile(
        profile_id="in-mobile-mysore",
        device_type=BrowserDeviceType.MOBILE,
        viewport=BrowserViewport(width=390, height=844),
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        country_code="IN",
        geolocation=BrowserGeolocation(latitude=12.2958, longitude=76.6394, accuracy=20),
        pincode="570001",
        location_label="Mysore",
    ).context_options()
    assert mobile["viewport"] == {"width": 390, "height": 844}
    assert mobile["is_mobile"] is True
    assert mobile["has_touch"] is True
    assert mobile["locale"] == "en-IN"
    assert mobile["timezone_id"] == "Asia/Kolkata"
    assert mobile["geolocation"] == {"latitude": 12.2958, "longitude": 76.6394, "accuracy": 20}
    assert mobile["permissions"] == ["geolocation"]

    mobile_profile = BrowserProfile(
        profile_id="in-mobile-mysore",
        device_type=BrowserDeviceType.MOBILE,
        viewport=BrowserViewport(width=390, height=844),
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        country_code="IN",
        geolocation=BrowserGeolocation(latitude=12.2958, longitude=76.6394, accuracy=20),
        pincode="570001",
        location_label="Mysore",
    )
    session, browser = session_with_pages([FakePage()])
    await session.capture(
        BrowserCaptureRequest(
            requested_url="https://www.amazon.in/s?k=diapers",
            page_type="amazon_serp",
            profile=mobile_profile,
        )
    )
    assert browser.context_options == [mobile]
    await session.close()


@pytest.mark.asyncio
async def test_capture_preserves_exact_html_redirect_metadata_and_screenshot() -> None:
    html = b"<html><body>fixture raw bytes: \xff</body></html>"
    page = FakePage(response=FakeResponse(body_bytes=html), final_url="https://www.amazon.in/final")
    session, browser = session_with_pages([page])

    result = await session.capture(
        BrowserCaptureRequest(
            requested_url="https://www.amazon.in/s?k=diapers",
            page_type="amazon_serp",
            profile=profile(),
            capture_screenshot=True,
        )
    )

    assert result.requested_url == "https://www.amazon.in/s?k=diapers"
    assert result.final_url == "https://www.amazon.in/final"
    assert result.status == 200
    assert result.html == html
    assert result.content_type == "text/html; charset=utf-8"
    assert result.captured_at.tzinfo is UTC
    assert result.page_type == "amazon_serp"
    assert result.profile_id == "in-desktop"
    assert result.challenge_detected is False
    assert result.screenshot == b"\x89PNG\r\nfixture"
    assert page.closed is True
    assert browser.context_options == [profile().context_options()]

    await session.close()
    assert browser.closed is True
    assert browser.contexts[0].closed is True
    assert session.active_context_count == 0


@pytest.mark.asyncio
async def test_non_allowlisted_target_is_rejected_before_browser_navigation() -> None:
    session, browser = session_with_pages([FakePage()])

    with pytest.raises(UnsupportedTargetError):
        await session.capture(request(url="https://amazon.in.evil.example/"))

    assert browser.contexts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("final_url", "title", "visible_text", "expected_kind"),
    [
        ("https://www.amazon.in/captcha", "Verify", "Verify you are human", ChallengeKind.CAPTCHA),
        ("https://www.amazon.in/ap/signin", "Sign in", "Continue", ChallengeKind.LOGIN_WALL),
        (
            "https://www.amazon.in/blocked",
            "Access denied",
            "Automated access",
            ChallengeKind.BOT_CHALLENGE,
        ),
    ],
)
async def test_challenge_capture_stops_safely_without_a_bypass(
    final_url: str,
    title: str,
    visible_text: str,
    expected_kind: ChallengeKind,
) -> None:
    page = FakePage(final_url=final_url, title=title, visible_text=visible_text)
    session, browser = session_with_pages([page])

    result = await session.capture(request())

    assert result.challenge.kind is expected_kind
    assert result.challenge_detected is True
    assert page.goto_calls == 1
    assert page.closed is True
    assert browser.contexts[0].closed is True
    assert session.active_context_count == 0


@pytest.mark.asyncio
async def test_navigation_failures_are_typed_sanitized_and_close_resources() -> None:
    timeout_page = FakePage(error=PlaywrightTimeoutError("secret https://signed.example"))
    timeout_session, timeout_browser = session_with_pages([timeout_page])
    with pytest.raises(BrowserNavigationTimeoutError) as timeout_error:
        await timeout_session.capture(request())
    assert "signed" not in str(timeout_error.value)
    assert timeout_error.value.__cause__ is None
    assert timeout_page.closed is True
    assert timeout_browser.contexts[0].closed is True

    failure_page = FakePage(error=PlaywrightError("token=super-secret"))
    failure_session, failure_browser = session_with_pages([failure_page])
    with pytest.raises(BrowserNavigationError) as failure_error:
        await failure_session.capture(request())
    assert "super-secret" not in str(failure_error.value)
    assert failure_error.value.__cause__ is None
    assert failure_page.closed is True
    assert failure_browser.contexts[0].closed is True


@pytest.mark.asyncio
async def test_concurrency_bound_and_context_reuse_are_enforced() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    activity = {"active": 0, "maximum": 0}
    first = FakePage(block=started, release=release, activity=activity)
    second = FakePage(block=started, release=release, activity=activity)
    session, browser = session_with_pages([first, second], max_concurrency=1)

    first_capture = asyncio.create_task(session.capture(request()))
    await started.wait()
    second_capture = asyncio.create_task(session.capture(request()))
    await asyncio.sleep(0)
    assert activity["maximum"] == 1
    assert browser.context_options == [profile().context_options()]

    release.set()
    await asyncio.gather(first_capture, second_capture)

    assert activity["maximum"] == 1
    assert len(browser.contexts) == 1
    await session.close()


@pytest.mark.asyncio
async def test_pacing_uses_injected_async_sleep_without_waiting() -> None:
    waits: list[float] = []

    async def record_sleep(seconds: float) -> None:
        waits.append(seconds)

    values = iter((10.0, 10.0))
    session, _ = session_with_pages(
        [], min_delay_seconds=2.0, sleep=record_sleep, clock=lambda: next(values)
    )

    await session._wait_for_pacing()
    await session._wait_for_pacing()

    assert waits == [2.0]


def test_challenge_detection_does_not_mark_normal_public_content() -> None:
    state = detect_challenge(
        final_url="https://www.amazon.in/s?k=diapers",
        title="Baby diapers",
        visible_text="Choose a comfortable diaper for your baby.",
    )
    assert state.kind is ChallengeKind.NONE


@pytest.mark.asyncio
async def test_real_chromium_lifecycle_starts_and_closes_without_network() -> None:
    session = PlaywrightBrowserSession(policy=policy())

    await session.start()
    assert session.is_started is True

    await session.close()
    assert session.is_started is False


def test_invalid_profile_settings_are_rejected() -> None:
    with pytest.raises(BrowserConfigurationError):
        BrowserProfile(profile_id=" ")
