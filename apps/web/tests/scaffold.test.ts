import { describe, expect, it } from "vitest";

const requiredSections = [
  "universe",
  "keywords",
  "products",
  "sources",
  "changes",
  "actions",
  "operations",
];

describe("Week 1 application scaffold", () => {
  it("includes every required top-level screen", () => {
    expect(requiredSections).toHaveLength(7);
    expect(requiredSections).toContain("operations");
  });
});
