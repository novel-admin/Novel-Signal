from __future__ import annotations

import pytest
from novel_signal.parsers.google_serp import GoogleSerpParser


def result(*, href: str, title: str = "Result", snippet: str | None = "Description") -> str:
    snippet_html = f'<div class="snippet">{snippet}</div>' if snippet is not None else ""
    return (
        '<div data-result="organic"><a href="'
        + href
        + '"><h3>'
        + title
        + "</h3></a>"
        + snippet_html
        + "</div>"
    )


def parse(html: str, **kwargs: object):
    return GoogleSerpParser(**kwargs).parse(html.encode())


def test_identity_single_organic_result_and_query() -> None:
    envelope = parse(
        '<input name="q" value="baby wipes">'
        + result(
            href="HTTPS://www.Novel.Example/products/x?colour=green#details", title=" Novel Wipes "
        ),
        novel_domains=("novel.example",),
    )
    assert envelope.parser_version == "google-serp-v1"
    assert envelope.page_type == "serp"
    assert envelope.records == (
        {
            "absolute_position": 1,
            "page_number": 1,
            "query": "baby wipes",
            "result_type": "organic",
            "title": "Novel Wipes",
            "url": "https://www.novel.example/products/x?colour=green",
            "displayed_domain": "novel.example",
            "snippet": "Description",
            "identity_match": "novel",
            "identity_domain": "novel.example",
            "result_metadata": {
                "source_dom_marker": "organic",
                "destination_host": "novel.example",
            },
        },
    )


def test_multiple_results_are_sequential_per_page_and_deterministic() -> None:
    html = result(href="https://one.example/a", title="One") + result(
        href="https://blog.competitor.example/b", title="Two", snippet=None
    )
    parser = GoogleSerpParser(page_number=3, competitor_domains=("competitor.example",))
    first = parser.parse(html.encode())
    assert first == parser.parse(html.encode())
    assert [item["absolute_position"] for item in first.records] == [1, 2]
    assert [item["page_number"] for item in first.records] == [3, 3]
    assert first.records[1]["displayed_domain"] == "blog.competitor.example"
    assert first.records[1]["snippet"] is None
    assert first.records[1]["identity_match"] == "competitor"


def test_google_redirect_is_unwrapped_and_invalid_destinations_are_skipped() -> None:
    target = "https%3A%2F%2Fshop.competitor.example%2Fp%3Fx%3D1"
    envelope = parse(
        result(href=f"https://www.google.com/url?q={target}")
        + result(href="https://www.google.com/search?q=ignored")
        + result(href="javascript:alert(1)")
        + result(href="data:text/plain,x")
        + result(href="https://user:pass@example.com/x"),
        competitor_domains=("competitor.example",),
    )
    assert len(envelope.records) == 1
    assert envelope.records[0]["url"] == "https://shop.competitor.example/p?x=1"
    assert envelope.records[0]["identity_domain"] == "competitor.example"
    assert envelope.warnings == ("Skipped Google result candidate without a safe destination URL",)


@pytest.mark.parametrize("parameter", ["q", "url"])
def test_explicit_google_url_endpoint_unwraps_both_supported_parameters(parameter: str) -> None:
    envelope = parse(
        result(href=f"https://google.co.in/url?{parameter}=https%3A%2F%2Fexample.com%2Fx%3Fa%3D1")
    )
    assert envelope.records[0]["url"] == "https://example.com/x?a=1"


@pytest.mark.parametrize("path", ["search", "preferences", "accounts"])
def test_google_navigation_paths_never_unwrap_targets(path: str) -> None:
    envelope = parse(result(href=f"https://www.google.com/{path}?q=https%3A%2F%2Fexample.com%2Fx"))
    assert envelope.records == ()


@pytest.mark.parametrize(
    "href",
    [
        "https://www.google.com/url?q=not-a-url",
        "https://example.com:bad/x",
        "https://user:pass@example.com/x",
    ],
)
def test_malformed_redirect_ports_and_credentials_are_rejected(href: str) -> None:
    assert parse(result(href=href)).records == ()


def test_modules_and_nested_candidates_are_excluded_without_shifting_positions() -> None:
    html = (
        '<div data-result="sponsored">Sponsored ' + result(href="https://ad.example") + "</div>"
        '<div data-module="shopping">' + result(href="https://shop.example") + "</div>"
        '<div data-module="related searches">' + result(href="https://related.example") + "</div>"
        '<div data-result="organic">'
        + result(href="https://nested.example")
        + "</div>"
        + result(href="https://accepted.example", title="Accepted")
    )
    records = parse(html).records
    assert len(records) == 2
    assert [record["url"] for record in records] == [
        "https://nested.example/",
        "https://accepted.example/",
    ]
    assert [record["absolute_position"] for record in records] == [1, 2]


@pytest.mark.parametrize(
    ("domain", "expected_match", "expected_domain"),
    [
        ("https://novel.example/a", "novel", "novel.example"),
        ("https://shop.novel.example/a", "novel", "novel.example"),
        ("https://competitor.example/a", "competitor", "competitor.example"),
        ("https://blog.competitor.example/a", "competitor", "competitor.example"),
        ("https://competitor.example.attacker.com/a", None, None),
        ("https://unrelated.example/a", None, None),
    ],
)
def test_identity_domain_matching_is_boundary_safe(
    domain: str, expected_match: str | None, expected_domain: str | None
) -> None:
    record = parse(
        result(href=domain),
        novel_domains=(".Novel.Example.",),
        competitor_domains=("competitor.example",),
    ).records[0]
    assert record["identity_match"] == expected_match
    assert record["identity_domain"] == expected_domain


@pytest.mark.parametrize(
    "domains",
    [("https://novel.example",), ("novel.example/path",), ("user@novel.example",), ("bad domain",)],
)
def test_invalid_configuration_is_rejected(domains: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="identity domain is invalid"):
        GoogleSerpParser(novel_domains=domains)
    with pytest.raises(ValueError, match="must not overlap"):
        GoogleSerpParser(novel_domains=("novel.example",), competitor_domains=("NOVEL.EXAMPLE",))


def test_no_query_script_style_and_missing_snippet_are_conservative() -> None:
    record = parse(
        "<script>secret query script</script><style>.snippet{bad}</style>"
        + result(href="https://example.com/a", title=" Visible ", snippet=None)
    ).records[0]
    assert record["query"] is None
    assert record["title"] == "Visible"
    assert record["snippet"] is None


def test_hidden_query_and_blank_heading_are_not_accepted_or_positioned() -> None:
    envelope = parse(
        '<input name="q" type="hidden" value="secret query">'
        + result(href="https://blank.example", title="   ")
        + result(href="https://accepted.example", title="Accepted")
    )
    assert len(envelope.records) == 1
    assert envelope.records[0]["query"] is None
    assert envelope.records[0]["absolute_position"] == 1
    assert "Skipped Google result candidate without a visible title" in envelope.warnings


def test_nested_configured_identity_is_ambiguous_without_configuration_overlap() -> None:
    envelope = parse(
        result(href="https://shop.example.com/product"),
        novel_domains=("example.com",),
        competitor_domains=("shop.example.com",),
    )
    record = envelope.records[0]
    assert record["identity_match"] is None
    assert record["identity_domain"] is None
    assert envelope.warnings == ("Google result had ambiguous configured-domain identity",)


def test_empty_and_invalid_utf8_are_rejected() -> None:
    parser = GoogleSerpParser()
    with pytest.raises(ValueError, match="HTML is empty"):
        parser.parse(b"")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        parser.parse(b"\xff")
