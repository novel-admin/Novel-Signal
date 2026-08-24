# Akanksh Week 1 Delivery Pack

Owner: Akanksh
Delivery window: 24-28 August 2026

## Outcome

Deliver the live data foundation that lets users compare every configured Novel SKU with its mapped Amazon competitors and track visibility across Amazon and Google organic search.

Akanksh owns:

- S1 Universe and Competitor Setup
- S2 Keyword Intelligence
- S3 Rank and Visibility Tracking
- S5 Listing and Content Intelligence
- S6 Price, Promo and Offer Intelligence
- S12 Collection Infrastructure
- Amazon SP-API
- Amazon Brand Analytics reports
- Google Search Console
- Playwright collection for public Amazon pages, Google organic results and configured competitor websites

## Required user journey

1. Import or configure Novel products, competitors, competitor ASINs and battle cards.
2. Build the keyword universe from Brand Analytics, Amazon Ads handoff data, Google Search Console and discovered public search terms.
3. Schedule data collection according to tracking tier.
4. Store the raw response before parsing.
5. Parse, validate and publish trusted observations.
6. Show Amazon ranks, Google ranks, listing differences, price differences, offers and availability.
7. Send published observations to Palguna's intelligence modules.

## Scope limits

- Amazon.in is the only marketplace this week.
- Meta, Facebook, Instagram and Google Ads Transparency Center are excluded.
- Google Search Console covers only Novel-owned verified properties.
- Google organic rank collection is public, logged-out collection through Playwright.
- Do not bypass CAPTCHA, login requirements or bot challenges. Back off and record a collection failure.
- Do not build BOS/SCM integration or shared authentication this week.
- Do not invent search volume. Preserve the source and confidence of every value.

## Build order

1. Finish source adapters and live credential checks.
2. Finish Playwright collectors and versioned parsers.
3. Connect collectors to S12 jobs and raw evidence.
4. Complete S2 automatic keyword ingestion and derived metrics.
5. Publish S3, S5 and S6 observations.
6. Complete the user-facing screens and live acceptance run.

Read the remaining files in this folder before coding.
