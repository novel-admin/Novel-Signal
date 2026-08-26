"use client";

import { useEffect, useState } from "react";
import { request } from "@novel-signal/api-client";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";

type Product = { id: string; name: string; internal_sku: string; marketplace_product_id: string | null; product_url: string | null; brand: string; category: string; pack_quantity: number | null; pack_unit: string | null; tracking_tier: string; archived_at: string | null };

export default function ProductsPage() {
  const [items, setItems] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { request<{ items: Product[] }>("/universe/products").then((data) => setItems(data.items)).catch((cause: Error) => setError(cause.message)); }, []);
  return <><div className="eyebrow">Tracked products</div><h1>Products</h1><p className="lede">Configured Universe identities. Collection status and measured observations appear in the intelligence modules, never as fallback product data.</p>{error ? <WorkError message={error} /> : items === null ? <WorkLoading /> : items.length === 0 ? <WorkEmpty message="No products have been configured yet." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Product</th><th>SKU / marketplace ID</th><th>Brand / category</th><th>Pack</th><th>Tier</th><th>Listing</th><th>Status</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.name}</td><td><div className="primary-cell"><strong>{item.internal_sku}</strong><span>{item.marketplace_product_id ?? "No marketplace ID configured"}</span></div></td><td>{item.brand} · {item.category}</td><td>{item.pack_quantity && item.pack_unit ? `${item.pack_quantity} ${item.pack_unit}` : "Not configured"}</td><td>{item.tracking_tier}</td><td>{item.product_url ? <a className="text-button" href={item.product_url} target="_blank" rel="noreferrer">Configured URL</a> : "Not configured"}</td><td><span className={`status ${item.archived_at ? "draft" : "approved"}`}>{item.archived_at ? "Archived" : "Active"}</span></td></tr>)}</tbody></table></div>}</>;
}
