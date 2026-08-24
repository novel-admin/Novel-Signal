# Akanksh Daily Delivery Plan

## Monday, 24 August

- Confirm S1 data readiness for all Novel SKUs, competitors, ASINs and battle cards.
- Implement live connection verification for SP-API, Brand Analytics and Google Search Console.
- Add source adapter tests with mocked HTTP responses.
- Agree on the handoff contracts with Palguna before either developer adds migrations.

End-of-day proof:

- Credentials verify without exposing secrets.
- One Novel SKU and one GSC property can be queried.
- Missing mapping report is visible.

## Tuesday, 25 August

- Complete SP-API raw fetching and parsing for owned listings, price and inventory.
- Complete Brand Analytics report request, polling, download and parsing.
- Complete GSC query ingestion.
- Store all source responses as raw evidence before normalization.

End-of-day proof:

- One live raw capture exists for each API.
- Re-running the same date window is idempotent.
- Brand Analytics and GSC queries appear in S2 with source lineage.

## Wednesday, 26 August

- Implement Playwright browser lifecycle and challenge detection.
- Implement Amazon SERP and product-page collectors/parsers.
- Implement Google organic SERP and configured public website collectors/parsers.
- Register S12 executors and schedule jobs from tracking targets.

End-of-day proof:

- Ten keywords and four ASINs produce raw evidence and parsed records.
- CAPTCHA or challenge fixture produces a recorded failure and no published observation.
- Golden parser fixtures pass.

## Thursday, 27 August

- Complete automatic keyword source merging and intent clustering.
- Build reverse-ASIN, Amazon SOV, Google visibility and keyword-gap calculations.
- Connect published data into S3, S5 and S6.
- Complete price-per-unit comparisons and listing diffs.
- Add change-event publication for Palguna.

End-of-day proof:

- A user can open one SKU and compare it with three competitors.
- Rank, listing and price history comes from retained evidence.
- Every keyword metric identifies its real source.

## Friday, 28 August

- Complete Akanksh-owned screens and freshness/evidence labels.
- Run database migrations against PostgreSQL.
- Run unit, integration, parser golden-file and frontend tests.
- Run a live end-to-end collection cycle.
- Fix only release-blocking defects.
- Hand Palguna a stable published-data API and current migration head.

Final proof:

- Every configured T1 target has a latest success or visible failure.
- Amazon and Google rank comparisons work.
- Amazon listing and price comparisons work.
- No dashboard uses unvalidated raw data.

## Daily coordination

- 10:00: agree on shared schema changes.
- 14:00: publish API examples and migration head.
- 18:00: demonstrate the day's vertical slice and list blockers plainly.

Do not merge a shared migration or response-schema change without Palguna reviewing it.
