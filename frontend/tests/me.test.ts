import { afterEach, describe, expect, it, vi } from "vitest";
import { getName, setName } from "@/lib/me";

function fakeStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("me", () => {
  it("trims, caps at 40 chars and clears on blank", () => {
    vi.stubGlobal("localStorage", fakeStorage());
    setName("  Furqan  ");
    expect(getName()).toBe("Furqan");
    setName("x".repeat(60));
    expect(getName()).toHaveLength(40);
    setName("   ");
    expect(getName()).toBe("");
  });
  it("survives storage that throws", () => {
    const boom = () => {
      throw new Error("blocked");
    };
    vi.stubGlobal("localStorage", { getItem: boom, setItem: boom, removeItem: boom });
    expect(() => setName("A")).not.toThrow();
    expect(getName()).toBe("");
  });
});
