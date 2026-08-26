from __future__ import annotations

import pytest
from novel_signal.parsers.public_web_page import PublicWebPageParser


def parse(html: str):
    return PublicWebPageParser().parse(html.encode())


def fixture(*, description: str = "Soft wipes for sensitive skin") -> str:
    return f"""
    <html><head>
      <title>  Acme   Baby Wipes </title>
      <link rel="canonical" href="HTTPS://Shop.Acme.Example/products/wipes?pack=3#details">
      <script>secret token and changing noise</script><style>.x {{ display:none }}</style>
    </head><body>
      <header><h2>Store navigation</h2><p>Not product content</p></header>
      <main id="product-detail">
        <h1> Acme Baby Wipes </h1><h2>Key Benefits</h2>
        <p>{description}</p>
        <ul class="features"><li> Aloe vera enriched </li><li>Aloe vera enriched</li></ul>
        <p hidden>Hidden offer</p><p style="display: none">Invisible price</p>
      </main>
      <footer><p>Legal noise</p></footer>
    </body></html>
    """


def test_visible_product_content_is_normalized_and_hashed() -> None:
    envelope = parse(fixture())
    record = envelope.records[0]
    assert envelope.parser_version == "public-web-page-v1"
    assert envelope.page_type == "public_web_page"
    assert record == {
        "url": "https://shop.acme.example/products/wipes?pack=3",
        "title": "Acme Baby Wipes",
        "headings": ["Acme Baby Wipes", "Key Benefits"],
        "product_content": ["Soft wipes for sensitive skin", "Aloe vera enriched"],
        "content_hash": record["content_hash"],
        "content_metadata": {
            "heading_count": 2,
            "product_block_count": 2,
            "canonical_url_present": True,
        },
    }
    assert len(record["content_hash"]) == 64
    assert "secret" not in str(record)
    assert "<html" not in str(record).lower()


def test_hash_is_stable_for_whitespace_and_non_visible_noise() -> None:
    first = parse(fixture()).records[0]
    second = parse(fixture().replace("changing noise", "different script noise")).records[0]
    spaced = parse(fixture().replace("Soft wipes", "Soft   wipes")).records[0]
    assert first["content_hash"] == second["content_hash"] == spaced["content_hash"]
    assert first == parse(fixture()).records[0]


def test_visible_product_change_changes_hash_and_extracted_block() -> None:
    before = parse(fixture()).records[0]
    after = parse(fixture(description="Biodegradable wipes for sensitive skin")).records[0]
    assert before["content_hash"] != after["content_hash"]
    assert after["product_content"][0] == "Biodegradable wipes for sensitive skin"


@pytest.mark.parametrize(
    "canonical",
    [
        "javascript:alert(1)",
        "https://user:pass@acme.example/x",
        "http://localhost/x",
        "http://127.0.0.1/x",
        "https://acme.example:bad/x",
    ],
)
def test_unsafe_canonical_url_is_not_published(canonical: str) -> None:
    envelope = parse(
        f'<html><head><title>Product</title><link rel="canonical" href="{canonical}"></head>'
        "<body><main><h1>Product</h1><p>Visible content</p></main></body></html>"
    )
    assert envelope.records[0]["url"] is None
    assert envelope.warnings == ("Public page did not expose a safe canonical URL",)


def test_page_without_selected_content_remains_unknown_not_fabricated() -> None:
    record = parse("<html><head><title>Company</title></head><body><nav>Menu</nav></body></html>")
    assert record.records[0]["headings"] == []
    assert record.records[0]["product_content"] == []


def test_empty_and_invalid_utf8_are_rejected() -> None:
    parser = PublicWebPageParser()
    with pytest.raises(ValueError, match="HTML is empty"):
        parser.parse(b"")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        parser.parse(b"\xff")
