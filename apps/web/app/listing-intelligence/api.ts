import type {Change,Comparison,Completeness,History,List,ProductOption,Snapshot} from "./types";
const base="/api/v1";
function message(body:unknown,status:number){if(body&&typeof body==="object"&&"detail" in body){const d=(body as {detail:unknown}).detail;if(d&&typeof d==="object"&&"message" in d)return String((d as {message:unknown}).message);}return `Request failed (${status})`;}
export async function request<T>(path:string):Promise<T>{const response=await fetch(`${base}${path}`,{cache:"no-store",credentials:"include"});const body:unknown=await response.json().catch(()=>null);if(!response.ok)throw new Error(message(body,response.status));return body as T;}
export async function dashboard(){const [snapshots,changes,products,competitors]=await Promise.all([request<List<Snapshot>>("/listing-intelligence/snapshots?limit=100"),request<List<Change>>("/listing-intelligence/changes?limit=100"),request<List<ProductOption>>("/universe/products?limit=200"),request<List<ProductOption>>("/universe/competitor-products?limit=200")]);return {snapshots,changes,products:products.items,competitors:competitors.items};}
export const detail=(id:string)=>request<Snapshot>(`/listing-intelligence/snapshots/${id}`);
export const history=(query:string)=>request<List<History>>(`/listing-intelligence/history?${query}`);
export const completeness=(query:string)=>request<Completeness>(`/listing-intelligence/completeness?${query}`);
export const comparison=(product:string,competitor:string)=>request<Comparison>(`/listing-intelligence/comparison?product_id=${product}&competitor_product_id=${competitor}`);
