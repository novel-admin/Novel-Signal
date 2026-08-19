# S6 Price Monitoring

## Purpose and architecture

S6 is the durable normalized price-observation layer. It stores observed marketplace pricing for an owned S1 `Product`, an S1 `CompetitorProduct`, or a deliberately unmapped marketplace identity. It never scrapes a marketplace and never creates fallback prices.

Production flow: **S12 collector → raw evidence → parser → normalized S6 observation → history/events/analytics/UI**. `source_job_id`, parser version, provider, source URL, and source metadata preserve lineage. S5 listing snapshots and S3 rank captures remain separate records; their price-like attributes are not automatically copied into S6.

## Entities and semantics

- `PriceObservation`: one marketplace price state at an observation time and geo/device context.
- `SellerOffer`: normalized seller-specific offers belonging to an observation.
- `PriceChangeEvent`: durable price movements and availability transitions.

Money uses fixed-precision `Decimal`/PostgreSQL `NUMERIC`, never float. Missing price is `null`, never zero. MRP/list price is only a reference value explicitly observed and never substituted for a selling price. Seller ordering does not imply Buy Box ownership; `is_featured_offer` is stored only when the normalized source explicitly supplies it.

Availability values are `available`, `limited`, `unavailable`, `out_of_stock`, and `unknown`. A missing price does not itself imply unavailability. Pincode/geo is part of the previous-observation context, so movements never compare two different geographies.

## Discount, coupon, shipping, and effective price

An explicit normalized discount is accepted only in the 0–100 range. Otherwise, when MRP is positive and selling price does not exceed MRP:

`discount = ((MRP - primary price) / MRP) × 100`, rounded half-up to two decimals.

If price exceeds MRP, derived discount is `null`. Effective price is accepted when explicitly normalized. Otherwise it is derived as `primary price + observed shipping - confirmed absolute coupon`, bounded at zero. Percentage, “up to”, bank, eligibility-dependent, and uncertain coupons are not subtracted. Without a primary price, effective price remains `null`.

Seller count is derived from unique seller identities when offers exist. If an explicit seller count and offers are both supplied, they must match. Featured/primary flags are never inferred.

## Movement, freshness, statistics, and comparison

The first observation is a quiet baseline. Later observations in the same marketplace identity, geo, and capture context can create `price_increase`, `price_decrease`, `became_available`, or `became_unavailable`. Absolute movement is `new - previous`; percentage movement is `(new - previous) / previous × 100`, rounded to two decimals. Null prices never participate in numeric statistics.

Observations at most 240 minutes old are `fresh`; older observations are `stale`. History is retained indefinitely. Metrics expose latest, minimum, maximum, average, count, latest MRP/discount/effective price, and last movement. Comparison returns only data-supported deterministic signals: owned cheaper/more expensive/same, unavailable sides, and stale sides. It never recommends repricing.

## API and frontend

Prefix: `/api/v1/price-monitoring`

- `GET /meta`
- `POST /observations`
- `GET /observations`
- `GET /observations/{id}`
- `GET /observations/{id}/offers`
- `GET /latest`
- `GET /history`
- `GET /metrics`
- `GET /events`
- `GET /comparison`

Frontend: `/price-monitoring`, with Current Prices, History, Seller Offers, Price Events, and Comparison tabs. It consumes only API records and displays `Unavailable` for absent prices.

## Manual PostgreSQL QA

1. Create an isolated QA database and run `alembic upgrade head` against it.
2. Create one owned product and one competitor product through S1 Universe.
3. POST an owned baseline for pincode `560001`: price `499`, MRP `599`, two offers, available.
4. POST a competitor baseline: price `529`, MRP `649`, three offers.
5. Verify current observations, seller offers, metrics, comparison, and all frontend tabs.
6. POST owned `449` with a changed seller count and confirmed absolute coupon; verify decrease event, history, min/max/average, and effective price.
7. POST an unavailable owned observation with `primary_price: null`; verify `became_unavailable` and that UI never displays zero.
8. POST an available observation; verify `became_available`.
9. POST a different price for a second pincode; verify no cross-geo movement and geo-specific latest/history.
10. Reuse an ingestion key and expect `409`. Submit negative money, discount above 100, mismatched seller count, and invalid date range and expect validation errors.
11. Delete only the isolated QA database after review; never delete shared development records.

## Limitations and guarantee

S6 contains no live marketplace provider, scraper, CAPTCHA handling, image processing, forecasting, or automatic repricing. Provider integration can publish normalized observations later. **No observed price means no price**: production code and UI never fabricate, estimate, randomize, or substitute a marketplace price.
