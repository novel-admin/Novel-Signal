from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from novel_signal.parsers.amazon_product import AmazonProductParser

FULL_PAGE = b"""
<html><head><meta name="asin" content="b0test0001"></head><body>
<input id="ASIN" value="B0TEST0001">
<span id="productTitle"> Novel   Baby Wipes </span>
<a id="bylineInfo">Visit the NOVEL Store</a>
<div id="wayfinding-breadcrumbs_container"><a>Baby</a><a>Wipes</a></div>
<div id="feature-bullets"><ul><li>Soft and gentle</li><li>Soft and gentle</li>
<li> </li><li>Plant based</li></ul></div>
<div id="productDescription">Gentle visible product description.</div>
<div id="aplus_feature"><h2>Why NOVEL</h2><p>Natural care</p></div>
<img id="landingImage" src="https://images.example/one.jpg#fragment" data-old-hires="https://images.example/one.jpg">
<img class="product image" src="https://images.example/two.jpg">
<div id="video-player" data-video="container"><video src="https://video.example/one.mp4"></video></div>
<div id="variation_color"><li title="Green">Green</li><li title="Blue">Blue</li></div>
<div id="variation_size"><button title="Large">Large</button></div>
<span id="priceblock_dealprice">Rs. 199.00</span>
<span id="priceblock_listprice">M.R.P.: Rs. 299.00</span><span class="discount">-33% off</span>
<div id="couponText">Apply Rs. 20 coupon</div>
<div id="deliveryMessage">FREE delivery Tomorrow</div>
<div id="availability">In stock.</div>
<a id="sellerProfileTriggerId" href="/sp?seller=SELLER123">Novel Retail</a>
<span>Featured offer</span>
<div data-offer="visible"><a class="seller" href="/sp?seller=SELLER123">Novel Retail</a>
<span class="offer-price">Rs. 199</span>
<span>Rs. 199</span><span>Prime</span></div>
<div data-offer="visible"><a class="seller" href="/sp?seller=SELLER123">Novel Retail</a>
<span class="offer-price">Rs. 199</span></div>
<div id="detailBullets_feature_div">Best Sellers Rank: #1,234 in Baby Wipes Pack of 3 80 ml</div>
</body></html>
"""


def parse(html: bytes = FULL_PAGE):
    return AmazonProductParser().parse(html)


def test_full_product_page_parses_s5_and_s6_ready_record() -> None:
    envelope = parse()
    record = envelope.records[0]

    assert envelope.parser_version == "amazon-product-v1"
    assert envelope.page_type == "product_detail"
    assert record["marketplace_product_id"] == "B0TEST0001"
    assert record["title"] == "Novel Baby Wipes"
    assert record["brand"] == "NOVEL"
    assert record["category_path"] == "Baby > Wipes"
    assert record["bullets"] == ["Soft and gentle", "Plant based"]
    assert record["key_features"] == record["bullets"]
    assert record["description"] == "Gentle visible product description."
    assert record["a_plus_present"] is True
    assert record["a_plus_sections"] == [{"text": "Why NOVEL Natural care"}]
    assert record["image_urls"] == [
        "https://images.example/one.jpg",
        "https://images.example/two.jpg",
    ]
    assert record["image_hashes"] == [
        hashlib.sha256(url.encode()).hexdigest() for url in record["image_urls"]
    ]
    assert record["image_count"] == 2
    assert record["video_present"] is True
    assert record["video_count"] == 1
    assert record["variation_count"] == 3
    assert record["variation_metadata"] == {
        "dimensions": {"color": ["Green", "Blue"], "size": ["Large"]}
    }
    assert record["primary_price"] == Decimal("199.00")
    assert record["mrp"] == Decimal("299.00")
    assert record["discount_percent"] == Decimal("33")
    assert record["coupon_text"] == "Apply Rs. 20 coupon"
    assert record["coupon_type"] == "absolute"
    assert record["coupon_value"] == Decimal("20")
    assert record["shipping_amount"] == Decimal("0")
    assert record["effective_price"] is None
    assert record["availability_status"] == "available"
    assert record["primary_seller_name"] == "Novel Retail"
    assert record["primary_seller_id"] == "SELLER123"
    assert record["is_featured_offer"] is True
    assert record["seller_count"] == 1
    assert record["offers"][0]["seller_name"] == "Novel Retail"
    assert record["offers"][0]["offer_price"] == Decimal("199")
    assert record["offers"][0]["prime_eligible"] is True
    assert record["content_metadata"] == {
        "bsr": {"rank": 1234, "category": "Baby Wipes Pack of 3 80 ml"},
        "pack_quantity": 3,
        "pack_unit": "ml",
        "pack_unit_quantity": "80",
    }


def test_asin_uses_product_link_fallback_and_rejects_missing_identity() -> None:
    fallback = b'<a href="https://www.amazon.in/dp/b0link0001">Product</a>'
    assert parse(fallback).records[0]["marketplace_product_id"] == "B0LINK0001"
    with pytest.raises(ValueError, match="identity is unavailable"):
        parse(b"<html><body>no identity</body></html>")
    with pytest.raises(ValueError, match="identity is unavailable"):
        parse(b'<input id="ASIN" value="not-an-asin">')


def test_prices_and_malformed_values_do_not_fabricate_money() -> None:
    html = b"""
    <input id="ASIN" value="B0PRICE001"><span id="priceblock_dealprice">Rs. malformed</span>
    <span id="priceblock_listprice">MRP Rs. malformed</span><span id="availability">In stock</span>
    """
    record = parse(html).records[0]
    assert record["primary_price"] is None
    assert record["mrp"] is None
    assert record["shipping_amount"] is None
    assert "Malformed primary price ignored" in parse(html).warnings


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Out of stock.", "out_of_stock"),
        ("Currently unavailable.", "unavailable"),
        ("Only 2 left in stock.", "limited"),
        ("In stock.", "available"),
        ("", "unknown"),
    ],
)
def test_availability_mappings_are_conservative(text: str, expected: str) -> None:
    html = f'<input id="ASIN" value="B0AVAIL001"><div id="availability">{text}</div>'.encode()
    assert parse(html).records[0]["availability_status"] == expected


@pytest.mark.parametrize(
    ("coupon", "coupon_type", "value"),
    [
        ("Save Rs. 30 coupon", "absolute", Decimal("30")),
        ("Save 15% coupon", "percentage", Decimal("15")),
        ("Apply coupon at checkout", "uncertain", None),
    ],
)
def test_coupon_parsing(coupon: str, coupon_type: str, value: Decimal | None) -> None:
    html = f'<input id="ASIN" value="B0COUPON01"><div id="couponText">{coupon}</div>'.encode()
    record = parse(html).records[0]
    assert record["coupon_type"] == coupon_type
    assert record["coupon_value"] == value


def test_no_seller_identity_does_not_create_an_offer() -> None:
    html = (
        b'<input id="ASIN" value="B0OFFER000">'
        b'<div data-offer="visible"><span>Rs. 99</span></div>'
    )
    record = parse(html).records[0]
    assert record["offers"] == []
    assert record["seller_count"] is None


@pytest.mark.parametrize(
    ("unrelated",),
    [
        ('<span class="list-price">Rs. 299</span>',),
        ('<span class="coupon">Rs. 20 coupon</span>',),
        ('<span class="shipping">Rs. 40 delivery</span>',),
    ],
)
def test_offer_price_requires_explicit_offer_price_evidence(unrelated: str) -> None:
    html = (
        '<input id="ASIN" value="B0OFFER001">'
        '<div data-offer="visible"><a class="seller">Seller One</a>'
        f"{unrelated}</div>"
    ).encode()
    offer = parse(html).records[0]["offers"][0]
    assert offer["offer_price"] is None


def test_nested_video_marker_counts_one_video_once() -> None:
    html = b"""
    <input id="ASIN" value="B0VIDEO000">
    <div data-video="product"><div><video src="https://video.example/one.mp4"></video></div></div>
    """
    record = parse(html).records[0]
    assert record["video_count"] == 1
    assert record["video_present"] is True


def test_variation_count_is_distinct_option_labels_across_dimensions() -> None:
    html = b"""
    <input id="ASIN" value="B0VARY0000">
    <div id="variation_color"><li title="Green">Green</li><li title="Blue">Blue</li></div>
    <div id="variation_style"><button title="Green">Green</button>
    <button title="Large">Large</button></div>
    """
    record = parse(html).records[0]
    assert record["variation_count"] == 3
    assert record["variation_metadata"] == {
        "dimensions": {"color": ["Green", "Blue"], "style": ["Green", "Large"]}
    }


def test_featured_offer_preserves_tri_state() -> None:
    assert parse(b'<input id="ASIN" value="B0FEAT0001">').records[0]["is_featured_offer"] is None
    html = b'<input id="ASIN" value="B0FEAT0001"><div data-featured-offer="false">Offer</div>'
    assert parse(html).records[0]["is_featured_offer"] is False


def test_parser_is_deterministic_and_rejects_invalid_input() -> None:
    parser = AmazonProductParser()
    assert parser.parse(FULL_PAGE) == parser.parse(FULL_PAGE)
    with pytest.raises(ValueError, match="HTML is empty"):
        parser.parse(b"")
    with pytest.raises(ValueError, match="not valid UTF-8"):
        parser.parse(b"\xff")
