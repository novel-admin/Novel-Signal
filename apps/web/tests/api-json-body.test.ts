import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestMock } = vi.hoisted(() => ({ requestMock: vi.fn() }));

vi.mock("@novel-signal/api-client", () => ({
  apiBaseUrl: "https://api.example.test/api/v1",
  request: requestMock,
}));

import { apiRequest as universeRequest, validateCsv } from "../app/universe/api";
import { request as collectionRequest } from "../app/collection/api";

describe("JSON request bodies", () => {
  beforeEach(() => {
    requestMock.mockReset();
    requestMock.mockResolvedValue({});
  });

  it("converts the Universe form's serialized JSON into an object before sending", async () => {
    const product = { internal_sku: "SKU-1", tracking_tier: "T2" };

    await universeRequest("/universe/products", {
      method: "POST",
      body: JSON.stringify(product),
    });

    expect(requestMock).toHaveBeenCalledWith("/universe/products", {
      method: "POST",
      body: product,
      headers: undefined,
    });
  });

  it("sends CSV text as a JSON object for validation", async () => {
    await validateCsv("products", "internal_sku,name\nSKU-1,Product");

    expect(requestMock).toHaveBeenCalledWith("/universe/csv/products/dry-run", {
      method: "POST",
      body: { csv_text: "internal_sku,name\nSKU-1,Product" },
      headers: undefined,
    });
  });

  it("sends collection mutations as JSON objects too", async () => {
    await collectionRequest("/collection/resync", {
      method: "POST",
      body: JSON.stringify({ force: true }),
    });

    expect(requestMock).toHaveBeenCalledWith("/collection/resync", {
      method: "POST",
      body: { force: true },
      headers: undefined,
    });
  });
});
