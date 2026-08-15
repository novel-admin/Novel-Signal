import { describe, expect, it } from "vitest";

import { paginationRange } from "../app/universe/universe-client";

describe("Universe pagination", () => {
  it("exposes the second page for datasets larger than fifty records", () => {
    expect(paginationRange({ total: 75, limit: 50, offset: 50 })).toEqual({
      start: 51,
      end: 75,
    });
  });
});
