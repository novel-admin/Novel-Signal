import type {Change,Comparison,Completeness,History,List,ProductOption,Snapshot} from "./types";
import { request as authenticatedRequest } from "@novel-signal/api-client";
export function request<T>(path:string):Promise<T>{return authenticatedRequest<T>(path,{cache:"no-store"});}
export async function dashboard(){const [snapshots,changes,products,competitors]=await Promise.all([request<List<Snapshot>>("/listing-intelligence/snapshots?limit=100"),request<List<Change>>("/listing-intelligence/changes?limit=100"),request<List<ProductOption>>("/universe/products?limit=200"),request<List<ProductOption>>("/universe/competitor-products?limit=200")]);return {snapshots,changes,products:products.items,competitors:competitors.items};}
export const detail=(id:string)=>request<Snapshot>(`/listing-intelligence/snapshots/${id}`);
export const history=(query:string)=>request<List<History>>(`/listing-intelligence/history?${query}`);
export const completeness=(query:string)=>request<Completeness>(`/listing-intelligence/completeness?${query}`);
export const comparison=(product:string,competitor:string)=>request<Comparison>(`/listing-intelligence/comparison?product_id=${product}&competitor_product_id=${competitor}`);
