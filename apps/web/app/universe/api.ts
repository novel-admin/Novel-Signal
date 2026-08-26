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
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(body, response.status));
  return body as T;
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
