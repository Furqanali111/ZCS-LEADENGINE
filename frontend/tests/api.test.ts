import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, listOwners } from "@/lib/api";

const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
});

const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  store.clear();
  vi.restoreAllMocks();
});

describe("api request", () => {
  it("sends X-Salesperson percent-encoded when a name is set", async () => {
    store.set("zcs_name", "Zoë Ali");
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(reply(200, []));
    await listOwners();
    const init = f.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-Salesperson"]).toBe(encodeURIComponent("Zoë Ali"));
  });

  it("omits the header when no name is set", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(reply(200, []));
    await listOwners();
    const headers = ((f.mock.calls[0][1] ?? {}) as RequestInit).headers as Record<string, string> | undefined;
    expect(headers?.["X-Salesperson"]).toBeUndefined();
  });

  it("maps the backend error JSON to ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      reply(409, { error: { code: "already_claimed", message: "Taken", fields: { owner: "x" } } }),
    );
    const e = await listOwners().catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ code: "already_claimed", status: 409, message: "Taken", fields: { owner: "x" } });
  });

  it("falls back to a generic error for a non-JSON body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("oops", { status: 500 }));
    const e = await listOwners().catch((x) => x);
    expect(e).toMatchObject({ code: "http_error", status: 500 });
  });

  it("maps a network failure to network_error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fail"));
    const e = await listOwners().catch((x) => x);
    expect(e).toMatchObject({ code: "network_error" });
  });
});
