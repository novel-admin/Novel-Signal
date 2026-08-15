# S2 Keyword Intelligence ER diagram

```mermaid
erDiagram
    KEYWORD ||--|{ KEYWORD_SOURCE : "has provenance"
    KEYWORD ||--o{ TRACKING_TARGET : configures
    PRODUCT ||--o{ TRACKING_TARGET : "optional owned target"
    COMPETITOR_PRODUCT ||--o{ TRACKING_TARGET : "optional external target"
    KEYWORD ||--o{ SERP_CAPTURE : "FUTURE S3 observation"

    KEYWORD {
        uuid id PK
        string keyword_text
        string normalized_text "active unique with marketplace"
        enum marketplace
        string category "nullable"
        enum tier
        enum tracking_status
        enum intent_cluster
        integer volume_estimate "nullable estimate"
        json trend_metadata "nullable"
        integer seasonality_index "nullable"
        timestamp archived_at "nullable"
    }
    KEYWORD_SOURCE {
        uuid id PK
        uuid keyword_id FK
        enum source_type
        string source_reference
        timestamp discovered_at
        json source_metadata "nullable"
    }
    TRACKING_TARGET {
        uuid id PK
        uuid keyword_id FK
        uuid product_id FK "exactly one target"
        uuid competitor_product_id FK "exactly one target"
        integer cadence_minutes "positive; Week 1 = 240"
        boolean enabled
        timestamp archived_at "nullable"
    }
    SERP_CAPTURE {
        uuid id PK "FUTURE - not implemented"
        uuid keyword_id FK
        timestamp captured_at
        json result_observations
        string collection_provenance
    }
```

Active partial unique constraints protect Keyword identity and each target mapping. Foreign keys
use `RESTRICT` for configured targets; source rows use `CASCADE` only at the database relationship
level, while the application exposes no hard-delete operation.

`SERP_CAPTURE` is intentionally shown as a future S3 boundary, not as an implemented S2 table.
SOV, rank history, and keyword gaps are derived from multiple timestamped captures plus S1 listing
identity; they do not belong on the Keyword master.
