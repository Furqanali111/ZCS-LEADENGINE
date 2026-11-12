import { describe, expect, it } from "vitest";
import { hostOf, formatPhone, safeHttpUrl } from "@/lib/format";
import { isOverdue, todayLocal } from "@/lib/dates";

describe("formatPhone", () => {
  it("formats 10 digits and strips a leading 1", () => {
    expect(formatPhone("3055551234")).toBe("(305) 555-1234");
    expect(formatPhone("+1 (305) 555-1234")).toBe("(305) 555-1234");
  });
  it("returns odd input unchanged and a dash for empty", () => {
    expect(formatPhone("555-1234")).toBe("555-1234");
    expect(formatPhone(null)).toBe("-");
  });
});

describe("safeHttpUrl", () => {
  it("allows http and https only", () => {
    expect(safeHttpUrl("https://a.com/x")).toBe("https://a.com/x");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("not a url")).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
  });
});

describe("hostOf", () => {
  it("drops www and falls back to the input", () => {
    expect(hostOf("https://www.clinic.com/about")).toBe("clinic.com");
    expect(hostOf("clinic")).toBe("clinic");
  });
});

describe("dates", () => {
  it("todayLocal is YYYY-MM-DD", () => {
    expect(todayLocal()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
  it("isOverdue compares against today", () => {
    expect(isOverdue(null)).toBe(false);
    expect(isOverdue("2000-01-01")).toBe(true);
    expect(isOverdue("2999-01-01")).toBe(false);
    expect(isOverdue(todayLocal())).toBe(false);
  });
});
