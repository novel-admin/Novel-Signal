import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(__dirname, "..");

function read(path: string): string {
  return readFileSync(join(root, path), "utf8");
}

describe("PM plan discovery and gaps screens", () => {
  it("exposes a discovery queue backed by the proposal API", () => {
    const page = read("app/discovery/page.tsx");
    expect(page).toContain("/universe/competitor-proposals?status=pending");
    expect(page).toContain("/universe/competitor-proposals/build");
    expect(page).toContain("Approve");
    expect(page).toContain("unapproved proposals stay out of scorecards");
  });

  it("exposes a gaps screen backed by evidence-linked gaps", () => {
    const page = read("app/gaps/page.tsx");
    expect(page).toContain('loadRows("/gaps")');
    expect(page).toContain("Revenue at stake");
  });

  it("links discovery and gaps in primary navigation", () => {
    const sidebar = read("components/AppSidebar.tsx");
    expect(sidebar).toContain('"/discovery"');
    expect(sidebar).toContain('"/gaps"');
  });

  it("shows the active source mode instead of claiming live data", () => {
    const banner = read("components/SourceModeBanner.tsx");
    expect(banner).toContain("Public Amazon mode");
    expect(banner).toContain("not connected");
    expect(banner).toContain("unknown");
    const shell = read("components/AppShell.tsx");
    expect(shell).toContain("SourceModeBanner");
  });
});
