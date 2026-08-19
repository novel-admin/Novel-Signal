"use client";

import { useEffect, useState } from "react";
import { request } from "@novel-signal/api-client";
import { WorkEmpty, WorkError, WorkLoading } from "../../components/WorkStates";

type Product = { id: string; name: string; internal_sku: string; marketplace_product_id: string | null; brand: string; category: string };

export default function ProductsPage() {
  const [items, setItems] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { request<{ items: Product[] }>("/universe/products").then((data) => setItems(data.items)).catch((cause: Error) => setError(cause.message)); }, []);
  return <><div className="eyebrow">Tracked products</div><h1>Products</h1><p className="lede">Review the Novel products included in the Week 1 tracking universe.</p>{error ? <WorkError message={error} /> : items === null ? <WorkLoading /> : items.length === 0 ? <WorkEmpty message="No products have been configured yet." /> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Product</th><th>SKU</th><th>ASIN</th><th>Brand</th><th>Category</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.internal_sku}</td><td>{item.marketplace_product_id ?? "-"}</td><td>{item.brand}</td><td>{item.category}</td></tr>)}</tbody></table></div>}</>;
}
