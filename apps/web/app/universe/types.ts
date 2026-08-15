export type Marketplace = "amazon_in";
export type TrackingTier = "T1" | "T2" | "T3";
export type PositioningTier = "premium" | "mid" | "value" | "unknown";
export type BattleCardStatus = "draft" | "approved";

export type Timestamped = {
  id: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type Competitor = Timestamped & {
  name: string;
  parent_company: string | null;
  amazon_store_url: string | null;
  amazon_seller_id: string | null;
  category_presence: string | null;
  positioning_tier: PositioningTier;
  threat_rating: number | null;
  analyst_owner: string | null;
  notes: string | null;
};

export type Product = Timestamped & {
  internal_sku: string;
  name: string;
  brand: string;
  category: string;
  marketplace: Marketplace;
  marketplace_product_id: string | null;
  product_url: string | null;
  pack_quantity: number | null;
  pack_unit: string | null;
  tracking_tier: TrackingTier;
};

export type CompetitorProduct = Timestamped & {
  competitor_id: string;
  name: string;
  brand: string;
  category: string;
  marketplace: Marketplace;
  marketplace_product_id: string | null;
  product_url: string | null;
  pack_quantity: number | null;
  pack_unit: string | null;
  tracking_tier: TrackingTier;
};

export type BattleCardItem = Timestamped & {
  competitor_product_id: string;
  priority_order: number | null;
  same_pack_basis: boolean;
  same_price_band: boolean;
  same_category: boolean;
  same_use_case: boolean;
  notes: string | null;
  competitor_product: CompetitorProduct;
};

export type BattleCard = Timestamped & {
  product_id: string;
  name: string;
  status: BattleCardStatus;
  comparison_notes: string | null;
  product: Product;
  items: BattleCardItem[];
};

export type ListResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type UniverseData = {
  competitors: Competitor[];
  products: Product[];
  competitorProducts: CompetitorProduct[];
  battleCards: BattleCard[];
  pagination: Record<"competitors" | "products" | "competitor-products" | "battle-cards", {
    total: number;
    limit: number;
    offset: number;
  }>;
};

export type CsvRowError = {
  row: number;
  field: string;
  code: string;
  message: string;
};

export type CsvValidationResult = {
  valid: boolean;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  errors: CsvRowError[];
};

export type CsvImportResult = {
  imported_rows: number;
  entity: string;
};
