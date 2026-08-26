"""Deterministic, offline parser for conservative Google organic-result HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from novel_signal.parsers.base import ParsedEnvelope

_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source"}


class GoogleSerpParser:
    """Parse only explicit, normal organic web-result candidates."""

    platform = "google"
    page_type = "serp"
    version = "google-serp-v1"

    def __init__(
        self,
        *,
        page_number: int = 1,
        novel_domains: tuple[str, ...] = (),
        competitor_domains: tuple[str, ...] = (),
    ) -> None:
        if page_number < 1:
            raise ValueError("Google SERP page number must be positive")
        self.page_number = page_number
        self.novel_domains = _domains(novel_domains)
        self.competitor_domains = _domains(competitor_domains)
        if set(self.novel_domains) & set(self.competitor_domains):
            raise ValueError("Google SERP identity domains must not overlap")

    def parse(self, raw: bytes) -> ParsedEnvelope:
        if not raw:
            raise ValueError("Google SERP HTML is empty")
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Google SERP HTML is not valid UTF-8") from None
        document = _Tree()
        try:
            document.feed(html)
            document.close()
        except Exception:
            raise ValueError("Google SERP HTML could not be parsed") from None

        warnings: list[str] = []
        records: list[dict[str, Any]] = []
        for candidate in _candidates(document.root):
            if _excluded(candidate):
                continue
            link = _result_link(candidate)
            if link is None:
                continue
            title = _heading_text(link) or _heading_text(candidate)
            if title is None:
                warnings.append("Skipped Google result candidate without a visible title")
                continue
            url = _destination(link.attrs.get("href", ""))
            if url is None:
                warnings.append("Skipped Google result candidate without a safe destination URL")
                continue
            host = _displayed_domain(url)
            match, identity_domain, ambiguous = _identity(
                host, self.novel_domains, self.competitor_domains
            )
            if ambiguous:
                warnings.append("Google result had ambiguous configured-domain identity")
            metadata: dict[str, object] = {
                "source_dom_marker": _marker(candidate),
                "destination_host": host,
            }
            displayed_path = _snippet_path(candidate)
            if displayed_path:
                metadata["displayed_path"] = displayed_path
            records.append(
                {
                    "absolute_position": len(records) + 1,
                    "page_number": self.page_number,
                    "query": _query(document.root),
                    "result_type": "organic",
                    "title": title,
                    "url": url,
                    "displayed_domain": host,
                    "snippet": _snippet(candidate),
                    "identity_match": match,
                    "identity_domain": identity_domain,
                    "result_metadata": metadata,
                }
            )
        return ParsedEnvelope(
            parser_version=self.version,
            page_type=self.page_type,
            records=tuple(records),
            warnings=tuple(dict.fromkeys(warnings)),
        )


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def descendants(self) -> tuple[_Node, ...]:
        found: list[_Node] = []
        for child in self.children:
            found.append(child)
            found.extend(child.descendants())
        return tuple(found)

    def text(self) -> str:
        return _text(" ".join((*self.text_parts, *(child.text() for child in self.children)))) or ""


class _Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"}:
            self.ignored_depth += 1
        node = _Node(normalized, {key.lower(): value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if normalized not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == normalized:
                del self.stack[index:]
                break
        if normalized in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth and (value := _text(data)):
            self.stack[-1].text_parts.append(value)


def _domains(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(_domain(value) for value in values))
    return normalized


def _domain(value: str) -> str:
    candidate = value.strip().strip(".").lower()
    if not _DOMAIN.fullmatch(candidate):
        raise ValueError("Google SERP identity domain is invalid")
    return candidate


def _candidates(root: _Node) -> tuple[_Node, ...]:
    results: list[_Node] = []

    def walk(node: _Node, in_candidate: bool = False, in_excluded_module: bool = False) -> None:
        candidate = _candidate(node)
        excluded = in_excluded_module or _excluded(node)
        if candidate and not in_candidate and not excluded:
            results.append(node)
        for child in node.children:
            walk(child, in_candidate or candidate, excluded)

    walk(root)
    return tuple(results)


def _candidate(node: _Node) -> bool:
    marker = " ".join(
        node.attrs.get(name, "")
        for name in ("data-result", "data-google-result", "data-testid", "class", "role")
    ).lower()
    has_heading = any(child.tag == "h3" for child in node.descendants())
    has_link = any(child.tag == "a" and child.attrs.get("href") for child in node.descendants())
    return (
        has_heading
        and has_link
        and (
            "organic" in marker
            or "result" in marker
            or node.attrs.get("data-ved", "") != ""
            or " g " in f" {marker} "
        )
    )


def _excluded(node: _Node) -> bool:
    evidence = " ".join(
        value
        for key, value in node.attrs.items()
        if key in {"class", "id", "data-result", "data-module", "aria-label", "role"}
    ).lower()
    text = " ".join(node.text_parts).lower()
    markers = (
        "sponsored",
        "advertisement",
        "shopping",
        "product block",
        "local pack",
        "maps",
        "knowledge panel",
        "people also ask",
        "related searches",
        "ai overview",
        "generated answer",
        "pagination",
        "video-only",
        "image-only",
    )
    return any(marker in evidence for marker in markers) or text.startswith("sponsored")


def _result_link(node: _Node) -> _Node | None:
    for candidate in (node, *node.descendants()):
        if candidate.tag != "a" or not candidate.attrs.get("href"):
            continue
        if _heading(candidate) is not None:
            return candidate
    return None


def _heading(node: _Node) -> _Node | None:
    return next((child for child in (node, *node.descendants()) if child.tag == "h3"), None)


def _heading_text(node: _Node) -> str | None:
    heading = _heading(node)
    return _text(heading.text()) if heading is not None else None


def _destination(href: str) -> str | None:
    parsed = urlsplit(href.strip())
    if _google_host(parsed.hostname):
        if parsed.path.lower() != "/url":
            return None
        target = next(
            (
                value
                for key in ("q", "url")
                for value in parse_qs(parsed.query).get(key, [])
                if value
            ),
            None,
        )
        if target is None:
            return None
        parsed = urlsplit(target)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or not _hostname(parsed.hostname)
        or _google_host(parsed.hostname)
    ):
        return None
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        port_value = parsed.port
    except ValueError:
        return None
    port = f":{port_value}" if port_value is not None else ""
    return urlunsplit(
        (parsed.scheme.lower(), hostname + port, parsed.path or "/", parsed.query, "")
    )


def _hostname(value: str) -> bool:
    return bool(_DOMAIN.fullmatch(value.rstrip(".").lower()))


def _google_host(host: str | None) -> bool:
    return bool(host and re.fullmatch(r"(?:[a-z0-9-]+\.)*google\.[a-z.]+", host.lower()))


def _displayed_domain(url: str) -> str:
    host = urlsplit(url).hostname or ""
    normalized = host.rstrip(".").lower()
    return normalized[4:] if normalized.startswith("www.") else normalized


def _identity(
    host: str, novel: tuple[str, ...], competitor: tuple[str, ...]
) -> tuple[str | None, str | None, bool]:
    novel_matches = [domain for domain in novel if host == domain or host.endswith(f".{domain}")]
    competitor_matches = [
        domain for domain in competitor if host == domain or host.endswith(f".{domain}")
    ]
    if len(novel_matches) + len(competitor_matches) != 1:
        return None, None, bool(novel_matches or competitor_matches)
    if novel_matches:
        return "novel", novel_matches[0], False
    return "competitor", competitor_matches[0], False


def _snippet(node: _Node) -> str | None:
    for child in (node, *node.descendants()):
        marker = " ".join(
            child.attrs.get(name, "") for name in ("class", "data-snippet", "data-result-snippet")
        ).lower()
        if "snippet" in marker:
            return _text(child.text())
    return None


def _snippet_path(node: _Node) -> str | None:
    for child in (node, *node.descendants()):
        if "breadcrumb" in child.attrs.get("class", "").lower():
            return _text(child.text())
    return None


def _query(root: _Node) -> str | None:
    for node in (root, *root.descendants()):
        if (
            node.tag in {"input", "textarea"}
            and node.attrs.get("name", "").lower() == "q"
            and node.attrs.get("type", "").lower() != "hidden"
        ):
            return _text(node.attrs.get("value", "") or node.text())
    return None


def _marker(node: _Node) -> str:
    return next(
        (
            node.attrs[key]
            for key in ("data-result", "data-google-result", "data-testid", "class")
            if node.attrs.get(key)
        ),
        "organic_candidate",
    )


def _text(value: str) -> str | None:
    normalized = " ".join(value.split())
    return normalized or None
