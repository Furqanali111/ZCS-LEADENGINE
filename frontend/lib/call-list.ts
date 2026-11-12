import { listLeads, type Lead } from "@/lib/api";

export type CallItem = { lead: Lead; due: boolean };

// The list endpoint has no "has phone" filter, so fetch a wider page of top-scored new leads and filter here.
export async function getCallList(max = 8): Promise<CallItem[]> {
  const [due, fresh] = await Promise.all([
    listLeads({ follow_up: "due", sort: "follow_up", order: "asc", page_size: max }),
    listLeads({ crm_status: "new", sort: "score", order: "desc", page_size: 50 }),
  ]);
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
