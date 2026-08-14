# S1 Universe ER diagram

```mermaid
erDiagram
    COMPETITOR ||--o{ COMPETITOR_PRODUCT : owns
    PRODUCT ||--o{ BATTLE_CARD : anchors
    BATTLE_CARD ||--o{ BATTLE_CARD_ITEM : contains
    COMPETITOR_PRODUCT ||--o{ BATTLE_CARD_ITEM : compared_by

    COMPETITOR {
        uuid id PK
        string name "unique while active"
        string parent_company
        string amazon_seller_id
        string category_presence
        enum positioning_tier
        datetime archived_at
    }
    PRODUCT {
        uuid id PK
        string internal_sku "unique while active"
        enum marketplace
        string marketplace_product_id "marketplace identity, unique while active"
        enum tracking_tier
        datetime archived_at
    }
    COMPETITOR_PRODUCT {
        uuid id PK
        uuid competitor_id FK
        enum marketplace
        string marketplace_product_id "unique per competitor while active"
        enum tracking_tier
        datetime archived_at
    }
    BATTLE_CARD {
        uuid id PK
        uuid product_id FK
        string name
        enum status
        datetime archived_at
    }
    BATTLE_CARD_ITEM {
        uuid id PK
        uuid battle_card_id FK
        uuid competitor_product_id FK "unique mapping while active"
        int priority_order "non-negative"
        boolean same_pack_basis
        boolean same_price_band
        boolean same_category
        boolean same_use_case
        datetime archived_at
    }
```

Active-only unique indexes allow an archived identity to be replaced while preventing two active
records from using the same business identity. Restore operations re-check these constraints.
