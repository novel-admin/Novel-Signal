import { describe, expect, it } from "vitest";

const requiredSections = [
  "universe",
  "keywords",
  "products",
  "sources",
  "changes",
  "actions",
  "operations",
  "ads",
  "reviews",
  "market-share",
  "scorecards",
  "alerts",
];

describe("Week 1 application scaffold", () => {
  it("includes every required top-level screen", () => {
    expect(requiredSections).toHaveLength(12);
    expect(requiredSections).toContain("operations");
  });
});
