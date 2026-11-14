import { ApiError, claimLead, listLeads, type Lead } from "@/lib/api";

export type CallItem = { lead: Lead; due: boolean };

// Due follow-ups first, then top-scored new leads that have a phone. Extra rows cover suppressed leads and duplicates.
export async function getCallList(max = 8): Promise<CallItem[]> {
  // allSettled: if one list fails the other still shows; only fail when both do.
  const [dueR, freshR] = await Promise.allSettled([
    listLeads({ follow_up: "due", sort: "follow_up", order: "asc", page_size: max }),
    listLeads({ crm_status: "new", has_phone: "true", sort: "score", order: "desc", page_size: 50 }),
  ]);
  if (dueR.status === "rejected" && freshR.status === "rejected") throw dueR.reason;
  const due = dueR.status === "fulfilled" ? dueR.value : { items: [] as Lead[] };
  const fresh = freshR.status === "fulfilled" ? freshR.value : { items: [] as Lead[] };
  const seen = new Set<string>();
  const out: CallItem[] = [];
  const add = (lead: Lead, isDue: boolean) => {
    if (out.length >= max || seen.has(lead.id) || lead.suppressed || lead.crm_status === "do_not_contact") return;
    seen.add(lead.id);
    out.push({ lead, due: isDue });
  };
  due.items.forEach((l) => add(l, true));
  fresh.items.filter((l) => l.phone).forEach((l) => add(l, false));
  return out;
}

// The next lead for this salesperson: their own due follow-ups first, else the best unclaimed new lead (claimed on the spot).
// The claim is atomic on the server, so if someone else wins a lead in the meantime we just try the next one.
export async function claimNext(name: string, excludeId?: string): Promise<Lead | null> {
  const ok = (l: Lead) => l.id !== excludeId && !l.suppressed && l.crm_status !== "do_not_contact" && Boolean(l.phone);
  const mine = await listLeads({ owner: name, follow_up: "due", sort: "follow_up", order: "asc", page_size: 10 });
  const due = mine.items.find(ok);
  if (due) return due;
  const fresh = await listLeads({ owner: "none", crm_status: "new", has_phone: "true", sort: "score", order: "desc", page_size: 30 });
  for (const l of fresh.items.filter(ok).slice(0, 8)) {
    try {
      return await claimLead(l.id);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 409)) throw e;
    }
  }
  return null;
}
