"""Synthetic, sanitized Amazon-card structures used for offline parser tests."""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from novel_signal.parsers.amazon_serp import AmazonSerpParser


def parse(html: str, *, page_number: int = 1):
    return AmazonSerpParser(page_number=page_number).parse(html.encode("utf-8"))


def card(asin: str | None, content: str, *, attributes: str = "") -> str:
    asin_attribute = f' data-asin="{asin}"' if asin is not None else ""
    return f'<div data-component-type="s-search-result"{asin_attribute}{attributes}>{content}</div>'


def test_organic_result_has_s3_compatible_fields_and_expected_identity() -> None:
    envelope = parse(
        card(
            "B0ABC12345",
            """
            <h2>Novel Baby Wipes</h2>
            <span data-brand="NOVEL"></span>
            <span class="a-price"><span class="a-price-whole">₹1,299.50</span></span>
            <span class="a-text-price">M.R.P.: ₹1,999</span>
            <span>-35% off</span>
            <span class="a-icon-alt">4.4 out of 5 stars</span>
            <span>1,234 ratings</span>
            <span class="coupon">Save ₹50 with coupon</span>
            <span class="delivery">FREE delivery Tomorrow</span>
            <img src="https://images.example.test/item.jpg?size=200#ignored" />
            """,
        )
    )

    assert envelope.parser_version == "amazon-serp-v1"
    assert envelope.page_type == "serp"
    assert envelope.warnings == ()
    assert envelope.records == (
        {
            "absolute_position": 1,
            "page_number": 1,
            "marketplace_product_id": "B0ABC12345",
            "brand": "NOVEL",
            "placement_type": "organic",
            "badges": [],
            "amazons_choice_term": None,
            "displayed_price": Decimal("1299.50"),
            "mrp": Decimal("1999"),
            "discount_percent": Decimal("35"),
            "coupon": "Save ₹50 with coupon",
            "delivery_promise": "FREE delivery Tomorrow",
            "rating": Decimal("4.4"),
            "review_count": 1234,
            "thumbnail_hash": hashlib.sha256(
                b"https://images.example.test/item.jpg?size=200"
            ).hexdigest(),
            "result_metadata": {
                "title": "Novel Baby Wipes",
                "primary_image_url": "https://images.example.test/item.jpg?size=200",
                "source_dom_marker": "s-search-result",
            },
        },
    )


def test_positions_ignore_non_products_and_cards_without_valid_identity() -> None:
    envelope = parse(
        "".join(
            (
                card("B0ABC12345", "<h2>First</h2>"),
                '<div class="header">Results header</div>',
                card(None, "<h2>Missing identity</h2>"),
                card("B0DEF67890", "<h2>Second</h2>"),
            )
        )
    )

    assert [record["marketplace_product_id"] for record in envelope.records] == [
        "B0ABC12345",
        "B0DEF67890",
    ]
    assert [record["absolute_position"] for record in envelope.records] == [1, 2]
    assert envelope.warnings == ("Skipped Amazon SERP card 2 without a valid ASIN",)


def test_product_detail_link_is_a_conservative_asin_fallback() -> None:
    envelope = parse(
        card(
            None,
            '<a href="/dp/b0ghi12345?tag=fixture"><h2>Fallback</h2></a>',
        )
    )

    assert envelope.records[0]["marketplace_product_id"] == "B0GHI12345"


def test_sponsored_and_badge_evidence_maps_only_existing_s3_values() -> None:
    envelope = parse(
        card(
            "B0ABC12345",
            """
            <span>Sponsored Brand Video</span>
            <span>Best Seller</span>
            <span>Amazon's Choice for "baby wipes"</span>
            <span>Limited time deal</span>
            <span>New Arrival</span>
            <span data-badge="Climate Pledge Friendly">Climate Pledge Friendly</span>
            """,
        )
    )
    result = envelope.records[0]

    assert result["placement_type"] == "sponsored_brand_video"
    assert result["badges"] == [
        "best_seller",
        "amazons_choice",
        "limited_time_deal",
        "new_arrival",
        "sponsored",
    ]
    assert result["amazons_choice_term"] == "baby wipes"
    assert result["result_metadata"] == {
        "source_dom_marker": "s-search-result",
        "unmapped_badges": ["Climate Pledge Friendly"],
    }
    assert envelope.warnings == ("Amazon SERP card contained unmapped badge text",)


def test_deal_without_sponsored_evidence_remains_organic() -> None:
    result = parse(card("B0ABC12345", "<span>Deal</span>")).records[0]

    assert result["placement_type"] == "organic"
    assert result["badges"] == ["deal"]


def test_limited_time_deal_without_sponsored_evidence_remains_organic() -> None:
    result = parse(card("B0ABC12345", "<span>Limited time deal</span>")).records[0]

    assert result["placement_type"] == "organic"
    assert result["badges"] == ["limited_time_deal"]


@pytest.mark.parametrize(
    ("deal_label", "expected_badge"),
    [("Deal", "deal"), ("Limited time deal", "limited_time_deal")],
)
def test_sponsored_deal_keeps_sponsored_placement(
    deal_label: str, expected_badge: str
) -> None:
    result = parse(
        card("B0ABC12345", f"<span>Sponsored</span><span>{deal_label}</span>")
    ).records[0]

    assert result["placement_type"] == "sponsored_product"
    assert result["badges"] == [expected_badge, "sponsored"]


def test_malformed_optional_metrics_do_not_create_fake_values() -> None:
    result = parse(
        card(
            "B0ABC12345",
            """
            <span class="a-price">₹not-a-price</span>
            <span class="a-text-price">list price unavailable</span>
            <span>125% off</span>
            <span>9.9 out of 5 stars</span>
            <span>many ratings</span>
            <img src="javascript:bad" />
            """,
        )
    ).records[0]

    assert result["displayed_price"] is None
    assert result["mrp"] is None
    assert result["discount_percent"] is None
    assert result["rating"] is None
    assert result["review_count"] is None
    assert result["thumbnail_hash"] is None
    assert result["result_metadata"] == {"source_dom_marker": "s-search-result"}


def test_thumbnail_hash_is_deterministic_without_network_access() -> None:
    html = card("B0ABC12345", '<img src="HTTPS://IMAGES.EXAMPLE.TEST/path/image.jpg#fragment" />')

    first = parse(html).records[0]
    second = parse(html).records[0]

    assert first["thumbnail_hash"] == second["thumbnail_hash"]
    assert first["thumbnail_hash"] == hashlib.sha256(
        b"https://images.example.test/path/image.jpg"
    ).hexdigest()
    assert first["result_metadata"] == {
        "primary_image_url": "https://images.example.test/path/image.jpg",
        "source_dom_marker": "s-search-result",
    }


def test_parser_is_deterministic_and_supports_configured_page_numbers() -> None:
    html = card("B0ABC12345", "<h2>Stable</h2>")
    parser = AmazonSerpParser(page_number=2)

    assert parser.parse(html.encode("utf-8")) == parser.parse(html.encode("utf-8"))
    assert parser.parse(html.encode("utf-8")).records[0]["page_number"] == 2


@pytest.mark.parametrize("raw", [b"", b"\xff"])
def test_unusable_html_is_rejected_with_sanitized_error(raw: bytes) -> None:
    with pytest.raises(ValueError, match="Amazon SERP HTML"):
        AmazonSerpParser().parse(raw)


def test_invalid_page_number_is_rejected() -> None:
    with pytest.raises(ValueError, match="page number"):
        AmazonSerpParser(page_number=0)
