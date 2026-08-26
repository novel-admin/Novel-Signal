"""Deterministic parser for visible content on configured public websites."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from novel_signal.parsers.base import ParsedEnvelope

_SPACE = re.compile(r"\s+")
_CONTENT_MARKERS = (
    "product",
    "description",
    "feature",
    "detail",
    "specification",
    "benefit",
)
_NON_VISIBLE_TAGS = {"script", "style", "noscript", "template", "svg"}
_EXCLUDED_AREAS = {"nav", "header", "footer", "aside"}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
}


class PublicWebPageParser:
    platform = "public_web"
    page_type = "public_web_page"
    version = "public-web-page-v1"

    def parse(self, raw: bytes) -> ParsedEnvelope:
        if not raw:
            raise ValueError("Public website HTML is empty")
        try:
            html = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Public website HTML is not valid UTF-8") from None
        document = _Document()
        try:
            document.feed(html)
            document.close()
        except Exception:
            raise ValueError("Public website HTML could not be parsed") from None

        title = _first_text(document.root, "title")
        headings = _headings(document.root)
        product_content = _product_content(document.root)
        url = _canonical_url(document.root)
        normalized = {
            "title": title,
            "headings": headings,
            "product_content": product_content,
        }
        content_hash = hashlib.sha256(
            json.dumps(
                normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        record: dict[str, Any] = {
            "url": url,
            "title": title,
            "headings": headings,
            "product_content": product_content,
            "content_hash": content_hash,
            "content_metadata": {
                "heading_count": len(headings),
                "product_block_count": len(product_content),
                "canonical_url_present": url is not None,
            },
        }
        warnings = () if url is not None else ("Public page did not expose a safe canonical URL",)
        return ParsedEnvelope(
            parser_version=self.version,
            page_type=self.page_type,
            records=(record,),
            warnings=warnings,
        )


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def descendants(self) -> tuple[_Node, ...]:
        result: list[_Node] = []
        for child in self.children:
            result.append(child)
            result.extend(child.descendants())
        return tuple(result)

    def text(self) -> str | None:
        if _hidden(self):
            return None
        return _text(" ".join((*self.text_parts, *(child.text() or "" for child in self.children))))


class _Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        node = _Node(normalized, {key.lower(): value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if normalized not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == normalized:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if value := _text(data):
            self.stack[-1].text_parts.append(value)


def _product_content(root: _Node) -> list[str]:
    blocks: list[str] = []

    def visit(node: _Node, *, in_content: bool = False, excluded: bool = False) -> None:
        hidden = excluded or _hidden(node) or node.tag in _EXCLUDED_AREAS
        marker = " ".join(
            value
            for key, value in node.attrs.items()
            if key in {"id", "class", "role", "data-component", "data-testid"}
        ).lower()
        active = (
            in_content
            or node.tag in {"main", "article"}
            or any(token in marker for token in _CONTENT_MARKERS)
        )
        if not hidden and active and node.tag in {"p", "li", "dd"}:
            if value := node.text():
                blocks.append(value)
            return
        for child in node.children:
            visit(child, in_content=active, excluded=hidden)

    visit(root)
    return _dedupe(blocks)


def _headings(root: _Node) -> list[str]:
    headings: list[str | None] = []

    def visit(node: _Node, *, excluded: bool = False) -> None:
        hidden = excluded or _hidden(node) or node.tag in _EXCLUDED_AREAS
        if not hidden and node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            headings.append(node.text())
        for child in node.children:
            visit(child, excluded=hidden)

    visit(root)
    return _dedupe(headings)


def _canonical_url(root: _Node) -> str | None:
    for node in root.descendants():
        if node.tag != "link":
            continue
        rel = {item.lower() for item in node.attrs.get("rel", "").split()}
        if "canonical" in rel and (url := _safe_url(node.attrs.get("href", ""))):
            return url
    return None


def _safe_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or _internal_hostname(hostname)
    ):
        return None
    del port
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def _internal_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return not address.is_global


def _hidden(node: _Node) -> bool:
    style = node.attrs.get("style", "").replace(" ", "").lower()
    return (
        node.tag in _NON_VISIBLE_TAGS
        or "hidden" in node.attrs
        or node.attrs.get("aria-hidden", "").lower() == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )


def _first_text(root: _Node, tag: str) -> str | None:
    return next(
        (value for node in root.descendants() if node.tag == tag if (value := node.text())),
        None,
    )


def _text(value: str) -> str | None:
    normalized = _SPACE.sub(" ", value).strip()
    return normalized or None


def _dedupe(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is not None and (normalized := _text(value)) and normalized not in result:
            result.append(normalized)
    return result
