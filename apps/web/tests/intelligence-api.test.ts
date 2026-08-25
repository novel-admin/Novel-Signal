import { afterEach, describe, expect, it, vi } from "vitest";
import { loadRows, transitionAlert } from "../app/intelligence/api";

afterEach(() => vi.restoreAllMocks());

describe("intelligence API", () => {
  it("loads both page and list responses", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: "one" }] })))
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: "two" }])));
    await expect(loadRows("/scorecards")).resolves.toEqual([{ id: "one" }]);
    await expect(loadRows("/reviews")).resolves.toEqual([{ id: "two" }]);
  });

  it("acknowledges alerts through the transition endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ id: "a1", status: "acknowledged" })));
    await transitionAlert("a1", "acknowledged");
    expect(fetchMock.mock.calls[0][0]).toContain("/alerts/a1/transition");
    expect(fetchMock.mock.calls[0][1]?.body).toContain('"status":"acknowledged"');
  });
});
