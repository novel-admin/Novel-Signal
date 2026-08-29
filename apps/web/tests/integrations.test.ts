import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("integrations settings", () => {
  it("keeps credentials write-only and uses the workspace connection API", () => {
    const page = readFileSync("app/settings/integrations/page.tsx", "utf8");
    expect(page).toContain("/sources/connections");
    expect(page).toContain("Save encrypted credentials");
    expect(page).toContain("never returned");
    expect(page).not.toContain("decrypt_credentials");
  });
});
