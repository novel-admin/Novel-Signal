import type {
  BattleCard,
  Competitor,
  CompetitorProduct,
  CsvImportResult,
  CsvValidationResult,
  ListResponse,
  Product,
  UniverseData,
} from "./types";

import { apiBaseUrl, request } from "@novel-signal/api-client";

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, {
    ...init,
    body: init?.body,
    headers: init?.headers,
  });
}

type UniverseTab = "competitors" | "products" | "competitor-products" | "battle-cards";

export async function loadUniverse(
  includeArchived: boolean,
  offsets: Record<UniverseTab, number>,
): Promise<UniverseData> {
  const query = (tab: UniverseTab) => {
    const params = new URLSearchParams({ limit: "50", offset: String(offsets[tab]) });
    if (includeArchived) params.set("include_archived", "true");
    return `?${params.toString()}`;
  };
  const [competitors, products, competitorProducts, battleCards] = await Promise.all([
    apiRequest<ListResponse<Competitor>>(`/universe/competitors${query("competitors")}`),
    apiRequest<ListResponse<Product>>(`/universe/products${query("products")}`),
    apiRequest<ListResponse<CompetitorProduct>>(`/universe/competitor-products${query("competitor-products")}`),
    apiRequest<ListResponse<BattleCard>>(`/universe/battle-cards${query("battle-cards")}`),
  ]);
  return {
    competitors: competitors.items,
    products: products.items,
    competitorProducts: competitorProducts.items,
    battleCards: battleCards.items,
    pagination: {
      competitors,
      products,
      "competitor-products": competitorProducts,
      "battle-cards": battleCards,
    },
  };
}

export function csvUrl(entity: string, action: "template" | "export", includeArchived = false): string {
  const archived = action === "export" && includeArchived ? "?include_archived=true" : "";
  return `${apiBaseUrl}/universe/csv/${entity}/${action}${archived}`;
}

export function validateCsv(entity: string, csvText: string): Promise<CsvValidationResult> {
  return apiRequest(`/universe/csv/${entity}/dry-run`, {
    method: "POST",
    body: JSON.stringify({ csv_text: csvText }),
  });
}

export function importCsv(entity: string, csvText: string): Promise<CsvImportResult> {
  return apiRequest(`/universe/csv/${entity}/import`, {
    method: "POST",
    body: JSON.stringify({ csv_text: csvText }),
  });
}
