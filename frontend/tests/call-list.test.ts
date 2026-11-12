import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, claimLead, listLeads, type Lead } from "@/lib/api";
import { claimNext } from "@/lib/call-list";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  listLeads: vi.fn(),
  claimLead: vi.fn(),
}));

const lead = (id: string, o: Partial<Lead> = {}) =>
  ({ id, phone: "3055551234", suppressed: false, crm_status: "new", ...o }) as Lead;
const page = (...items: Lead[]) => ({ items }) as Awaited<ReturnType<typeof listLeads>>;

beforeEach(() => vi.resetAllMocks());

describe("claimNext", () => {
  it("returns my own due follow-up without claiming", async () => {
    vi.mocked(listLeads).mockResolvedValueOnce(page(lead("a")));
    expect((await claimNext("me"))?.id).toBe("a");
    expect(claimLead).not.toHaveBeenCalled();
  });

  it("skips suppressed, do_not_contact and phoneless leads", async () => {
    vi.mocked(listLeads)
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(
        page(lead("s", { suppressed: true }), lead("d", { crm_status: "do_not_contact" }), lead("p", { phone: null }), lead("ok")),
      );
    vi.mocked(claimLead).mockImplementation(async (id) => lead(id));
    expect((await claimNext("me"))?.id).toBe("ok");
    expect(claimLead).toHaveBeenCalledTimes(1);
  });

  it("tries the next lead after a 409", async () => {
    vi.mocked(listLeads).mockResolvedValueOnce(page()).mockResolvedValueOnce(page(lead("a"), lead("b")));
    vi.mocked(claimLead)
      .mockRejectedValueOnce(new ApiError("conflict", "taken", 409))
      .mockImplementationOnce(async (id) => lead(id));
    expect((await claimNext("me"))?.id).toBe("b");
  });

  it("rethrows non-409 errors", async () => {
    vi.mocked(listLeads).mockResolvedValueOnce(page()).mockResolvedValueOnce(page(lead("a")));
    vi.mocked(claimLead).mockRejectedValueOnce(new ApiError("boom", "x", 500));
    await expect(claimNext("me")).rejects.toMatchObject({ status: 500 });
  });

  it("returns null when nothing is left, and honours excludeId", async () => {
    vi.mocked(listLeads).mockResolvedValueOnce(page(lead("a"))).mockResolvedValueOnce(page());
    expect(await claimNext("me", "a")).toBeNull();
  });
});
