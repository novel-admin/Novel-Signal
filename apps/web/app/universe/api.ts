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

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

function errorMessage(body: unknown, status: number): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = body.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null && "message" in detail) {
      return String(detail.message);
    }
    if (Array.isArray(detail)) {
      return detail
        .map((entry) => {
          if (typeof entry === "object" && entry !== null && "msg" in entry) {
            return String(entry.msg);
          }
          return String(entry);
        })
        .join(" · ");
    }
  }
  return `Request failed (${status})`;
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(body, response.status));
  return body as T;
}

export async function loadUniverse(includeArchived: boolean): Promise<UniverseData> {
  const query = includeArchived ? "?include_archived=true" : "";
  const [competitors, products, competitorProducts, battleCards] = await Promise.all([
    apiRequest<ListResponse<Competitor>>(`/universe/competitors${query}`),
    apiRequest<ListResponse<Product>>(`/universe/products${query}`),
    apiRequest<ListResponse<CompetitorProduct>>(`/universe/competitor-products${query}`),
    apiRequest<ListResponse<BattleCard>>(`/universe/battle-cards${query}`),
  ]);
  return {
    competitors: competitors.items,
    products: products.items,
    competitorProducts: competitorProducts.items,
    battleCards: battleCards.items,
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
