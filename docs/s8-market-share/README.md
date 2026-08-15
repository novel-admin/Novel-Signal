# S8 market-share contracts

S8 consumes published BSR, price, review-velocity, and first-party Novel sales
observations. It does not scrape marketplaces or treat competitor units as
measured facts.

Every competitor units and revenue value is an estimate with low/point/high
bounds, an explicit confidence label, input coverage, and a model version.
Model fits and back-tests are immutable records. Repeating an estimate for the
same entity, date, and model version is idempotent.

The API exposes model fits, estimates, daily share rows, and back-tests under
`/market-share`. `segment_key` is a stable serialized segment identifier such
as `pack_size:2|price_band:500-999`; `all` represents the unsegmented category.
