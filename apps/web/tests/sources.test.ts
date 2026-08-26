import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("Week 2 sources screen", () => {
  it("uses the source registry and collection readiness APIs without exposing secrets", () => {
    const screen = readFileSync("app/sources/page.tsx", "utf8");
    expect(screen).toContain('const api = "/api/v1"');
    expect(screen).toContain('`${api}/sources`');
    expect(screen).toContain('`${api}/collection/readiness`');
    expect(screen).toContain("does not claim that a live credential verification has run");
    expect(screen).not.toContain("credentials_json");
  });
});
