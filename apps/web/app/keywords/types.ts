export type SourceType = "brand_analytics"|"amazon_ads"|"autocomplete"|"reverse_asin"|"google_keyword_planner"|"search_console"|"review_mining"|"regional_variant"|"manual";
export type Source = { id?: string; source_type: SourceType; source_reference: string; };
export type Keyword = { id:string; keyword_text:string; normalized_text:string; marketplace:"amazon_in"; category:string|null; tier:"T1"|"T2"|"T3"; tracking_status:"active"|"paused"; intent_cluster:string; volume_estimate:number|null; seasonality_index:number|null; notes:string|null; sources:Source[]; archived_at:string|null; };
export type TrackingTarget = { id:string; keyword_id:string; product_id:string|null; competitor_product_id:string|null; cadence_minutes:number; enabled:boolean; archived_at:string|null; };
export type ProductOption = { id:string; name:string; internal_sku?:string; marketplace_product_id?:string|null; archived_at:string|null; };
export type ListResponse<T> = {items:T[];total:number;limit:number;offset:number};
export type CsvResult = {valid:boolean;total_rows:number;valid_rows:number;invalid_rows:number;errors:{row:number;field:string;message:string}[]};
