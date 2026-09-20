import type { CsvResult, Keyword, ListResponse, ProductOption, TrackingTarget } from "./types";
import { apiBaseUrl, request as authenticatedRequest } from "@novel-signal/api-client";
const base = apiBaseUrl;
export function request<T>(path:string,init?:RequestInit):Promise<T>{return authenticatedRequest<T>(path,{...init,body:typeof init?.body==="string"?JSON.parse(init.body):init?.body});}
export async function load(includeArchived:boolean){const q=includeArchived?"?include_archived=true":"";const [keywords,targets,products,competitorProducts]=await Promise.all([request<ListResponse<Keyword>>(`/keywords${q}`),request<ListResponse<TrackingTarget>>(`/keywords/tracking-targets${q}`),request<ListResponse<ProductOption>>(`/universe/products${q}`),request<ListResponse<ProductOption>>(`/universe/competitor-products${q}`)]);return {keywords:keywords.items,targets:targets.items,products:products.items,competitorProducts:competitorProducts.items};}
export const csvUrl=(entity:string,action:"template"|"export",archived=false)=>`${base}/keywords/csv/${entity}/${action}${action==="export"&&archived?"?include_archived=true":""}`;
export const dryRun=(entity:string,csv_text:string)=>request<CsvResult>(`/keywords/csv/${entity}/dry-run`,{method:"POST",body:JSON.stringify({csv_text})});
export const importCsv=(entity:string,csv_text:string)=>request<{imported_rows:number}>(`/keywords/csv/${entity}/import`,{method:"POST",body:JSON.stringify({csv_text})});
