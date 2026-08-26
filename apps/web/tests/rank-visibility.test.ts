import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { formatMetric } from "../app/rank-visibility/rank-visibility-client";

describe("S3 rank and visibility", () => {
  it("has a routable page and sidebar navigation entry", () => {
    const root = join(process.cwd(), "app");
    expect(readFileSync(join(root, "rank-visibility", "page.tsx"), "utf8")).toContain(
      "RankVisibilityClient",
    );
    expect(readFileSync(join(root, "layout.tsx"), "utf8")).toContain(
      '["Rank & Visibility", "/rank-visibility"]',
    );
  });

  it("formats absent and percentage metrics without inventing values", () => {
    expect(formatMetric(null)).toBe("—");
    expect(formatMetric(75, "%")).toBe("75%");
  });

  it("wires measured Amazon and Google intelligence through normalized API routes", () => {
    const root = join(process.cwd(), "app", "rank-visibility");
    expect(readFileSync(join(root, "api.ts"), "utf8")).toContain("amazon-share-of-voice");
    expect(readFileSync(join(root, "api.ts"), "utf8")).toContain("google-domain-comparison");
    const screen = readFileSync(join(root, "rank-visibility-client.tsx"), "utf8");
    expect(screen).toContain("Measured Amazon public SERP captures");
    expect(screen).toContain("Measured public Google SERP evidence only");
  });
});
