import type {Comparison,Event,HistoryRow,List,Observation,PricePerUnitComparison,ProductOption} from "./types";
import { request as authenticatedRequest } from "@novel-signal/api-client";
export function request<T>(path:string):Promise<T>{return authenticatedRequest<T>(path,{cache:"no-store"});}
export async function dashboard(){const [observations,events,products,competitors]=await Promise.all([request<List<Observation>>("/price-monitoring/observations?limit=200"),request<List<Event>>("/price-monitoring/events?limit=200"),request<List<ProductOption>>("/universe/products?limit=200"),request<List<ProductOption>>("/universe/competitor-products?limit=200")]);return {observations,events,products:products.items,competitors:competitors.items}}
export const history=(query:string)=>request<List<HistoryRow>>(`/price-monitoring/history?${query}`);
export const comparison=(product:string,competitor:string,geo:string)=>request<Comparison>(`/price-monitoring/comparison?product_id=${product}&competitor_product_id=${competitor}${geo?`&geo_code=${encodeURIComponent(geo)}`:""}`);
export const pricePerUnit=(product:string,competitor:string,geo:string)=>request<PricePerUnitComparison>(`/price-monitoring/price-per-unit?product_id=${product}&competitor_product_id=${competitor}${geo?`&geo_code=${encodeURIComponent(geo)}`:""}`);
