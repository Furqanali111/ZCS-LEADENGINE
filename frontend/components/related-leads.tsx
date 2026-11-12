"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { statusTone, ToneBadge } from "@/components/tone-badge";
import { ApiError, getRelatedLeads, type RelatedLead } from "@/lib/api";
import { CRM_STATUSES } from "@/lib/constants";
import { useName } from "@/lib/me";
import { PANEL_CLASS } from "@/lib/ui";

const REASON_LABEL: Record<string, string> = {
  same_phone: "Same phone",
  same_name: "Same name",
  same_parent: "Same parent organization",
  same_official: "Same owner official",
  same_website: "Same website",
};

// Loads after the main lead so a slow query never delays the page.
export function RelatedLeads({ leadId }: { leadId: string }) {
  const me = useName();
  const [items, setItems] = useState<RelatedLead[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getRelatedLeads(leadId)
      .then((r) => live && setItems(r))
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Unknown error."));
    return () => {
      live = false;
    };
  }, [leadId]);

  const others = (items ?? []).filter((r) => r.owner && r.owner.toLowerCase() !== me.toLowerCase());
  const names = [...new Set(others.map((r) => r.owner))];
  const who = names.length === 1 ? names[0] : "Others are";

  return (
    <section aria-labelledby="related-h" className={PANEL_CLASS}>
      <h2 id="related-h" className="mb-2">Related leads</h2>
      {others.length > 0 && (
        <p role="status" className="mb-3 rounded-md bg-tone-warning-bg p-2.5 font-medium text-tone-warning-fg">
          {names.length === 1 ? `${who} is` : `${who}`} already working {others.length} related {others.length === 1 ? "lead" : "leads"} at this practice. Check before calling.
        </p>
      )}
      {error ? (
        <p role="alert" className="text-destructive">Could not load related leads. {error}</p>
      ) : !items ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-muted-foreground">No related leads found</p>
      ) : (
        <ul className="space-y-3">
          {items.map((r) => (
            <li key={r.id}>
              <Link href={`/leads/${r.id}`} className="font-medium text-primary underline underline-offset-4">
                {r.name}
              </Link>
              <span className="text-muted-foreground"> {[r.city, r.state].filter(Boolean).join(", ")}</span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {r.reasons.map((k) => (
                  <span key={k} className="rounded-full border px-2 py-0.5 text-xs">{REASON_LABEL[k] ?? k}</span>
                ))}
                <ToneBadge tone={statusTone(r.crm_status)}>{CRM_STATUSES.find((s) => s.value === r.crm_status)?.label ?? r.crm_status}</ToneBadge>
                {r.owner && <ToneBadge tone="warning">Owner: {r.owner}</ToneBadge>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
