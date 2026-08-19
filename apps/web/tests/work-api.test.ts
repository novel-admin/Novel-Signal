import { afterEach, describe, expect, it, vi } from "vitest";
import { createAction, loadActions, transitionAction } from "../app/work/api";

afterEach(() => vi.restoreAllMocks());

describe("Week 1 work API", () => {
  it("loads all action pages", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: "a1" }], next_cursor: "next" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: "a2" }], next_cursor: null }), { status: 200 }));

    await expect(loadActions()).resolves.toEqual([{ id: "a1" }, { id: "a2" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("creates an action from a change and transitions it", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "a1" }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "a1", status: "done" }), { status: 200 }));
    const change = { id: "c1" } as Parameters<typeof createAction>[0];

    await createAction(change, { title: "Review price" });
    await transitionAction("a1", "done", "Completed");

    expect(fetchMock.mock.calls[0][0]).toContain("/changes/c1/actions");
    expect(fetchMock.mock.calls[1][1]?.body).toContain('"status":"done"');
  });
});

