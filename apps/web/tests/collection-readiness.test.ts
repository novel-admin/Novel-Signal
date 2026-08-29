import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("collection readiness screen", () => {
  it("uses the database scheduler contract", () => {
    const client = readFileSync("app/collection/collection-client.tsx", "utf8");
    const api = readFileSync("app/collection/api.ts", "utf8");
    const types = readFileSync("app/collection/types.ts", "utf8");

    expect(client).toContain('label="Database scheduler"');
    expect(client).not.toContain('label="Redis"');
    expect(client).not.toContain('label="Celery"');
    expect(types).toContain("scheduler: ReadinessItem");
    expect(types).not.toContain("redis: ReadinessItem");
    expect(types).not.toContain("celery: ReadinessItem");
    expect(api).toContain('"/collection/resync"');
    expect(client).toContain("Resync now");
  });
});
