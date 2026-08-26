# Amazon-first demo design

## Goal

Deliver a real-data Amazon.in demonstration that starts from Novel-owned SKUs and produces an evidence-backed competitor view. The dashboard must work with public Amazon data now and accept Amazon seller and Ads credentials later without replacing the data model.

## First demo path

`Novel SKU -> seed keywords -> Amazon search/product capture -> raw evidence -> versioned parser -> published observations -> competitor candidates -> approval -> comparison dashboard`

The first live public-data slice covers search rank, sponsored presence, title, bullets, images, price, discount, coupon, rating, review count, BSR, badges, availability, and change history. Competitor candidates are proposed with evidence and confidence; they do not become active tracking records without approval.

## Source and safety boundary

Use official Amazon APIs when credentials are configured. Until then, use only approved public, logged-out Amazon.in pages. Apply allowlists, conservative delays, retries with jitter, and bounded concurrency. CAPTCHA, login walls, bot challenges, and blocked responses stop the attempt and create a collection failure. No challenge is bypassed and no reviewer identity is stored.

## Access control

The demo dashboard uses `DASHBOARD_ACCESS_CODE`. The backend verifies the code and issues a signed, HTTP-only cookie. The frontend only renders the dashboard after `/auth/session` confirms access. Empty access-code configuration keeps local automated development unlocked; deployed demos must set a non-empty code.

## Later credential activation

When Amazon SP-API, Ads API, and Brand Analytics credentials are added, the same raw-first pipeline will ingest own listings, orders/inventory where permitted, ads/search terms, and keyword reports. Measured, derived, estimated, and unknown values remain explicitly labelled.
