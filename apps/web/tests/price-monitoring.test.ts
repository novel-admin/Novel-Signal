import {readFileSync} from "node:fs";
import {describe,expect,it} from "vitest";
import {formatFreshness,formatMoney,formatMovement} from "../app/price-monitoring/price-monitoring-client";

describe("S6 Price Monitoring frontend",()=>{
 it("registers the route and preserves navigation",()=>{expect(readFileSync("app/price-monitoring/page.tsx","utf8")).toContain("Price Monitoring");expect(readFileSync("app/layout.tsx","utf8")).toContain('["Price Monitoring", "/price-monitoring"]')});
 it("never formats a missing price as zero",()=>{expect(formatMoney(null)).toBe("Unavailable");expect(formatMoney(undefined)).toBe("Unavailable")});
 it("formats currencies using the observation currency",()=>{expect(formatMoney("499","INR")).toContain("499");expect(formatMoney("12.5","USD")).toContain("12.5")});
 it("formats freshness and movement",()=>{expect(formatFreshness(42)).toBe("42 min ago");expect(formatFreshness(125)).toBe("2 hr ago");expect(formatMovement("-50","INR")).toContain("↓")});
});
