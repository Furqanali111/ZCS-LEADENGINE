"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy, PhoneCall } from "lucide-react";
import { Button } from "@/components/ui/button";
import { priorityTone, ToneBadge } from "@/components/tone-badge";
import { ApiError } from "@/lib/api";
import { getCallList, type CallItem } from "@/lib/call-list";
import { PRIORITIES } from "@/lib/constants";
import { formatPhone } from "@/lib/format";
import { PANEL_CLASS } from "@/lib/ui";
import { useCopy } from "@/lib/use-copy";

export function CallToday() {
  const [items, setItems] = useState<CallItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { copied, failed, copy } = useCopy();

  useEffect(() => {
    let live = true;
    getCallList()
      .then((r) => live && setItems(r))
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Could not load the call list."));
    return () => {
      live = false;
    };
  }, []);

  return (
    <section aria-labelledby="call-today" className={`${PANEL_CLASS} space-y-3`} aria-busy={!items && !error}>
      <div className="flex items-center gap-2">
        <PhoneCall aria-hidden className="size-5 text-primary" />
        <h2 id="call-today" className="text-base font-semibold">
          Call today
        </h2>
        <Link href="/leads" className="ml-auto text-sm underline underline-offset-4">
          See all
        </Link>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {!items && !error && <p className="text-sm text-muted-foreground">Loading call list...</p>}
      {items && items.length === 0 && (
        <p className="text-sm text-muted-foreground">Nobody to call right now. No follow-ups are due and no new lead with a phone is among the top 50. Run a search to find more.</p>
      )}
      {items && items.length > 0 && (
        <ul className="divide-y">
          {items.map(({ lead, due }) => {
            const phone = lead.phone ? formatPhone(lead.phone) : null;
            const priority = PRIORITIES.find((p) => p.value === lead.priority)?.label;
            return (
              <li key={lead.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                <div className="min-w-0 flex-1 basis-56">
                  <Link href={`/leads/${lead.id}`} className="block truncate font-medium underline-offset-4 hover:underline">
                    {lead.name}
                  </Link>
                  <p className="text-sm text-muted-foreground">
                    {[lead.city, lead.state].filter(Boolean).join(", ") || "Location unknown"}
                    {due && <span className="ml-2 font-medium text-orange-800 dark:text-orange-300">Follow-up due</span>}
                  </p>
                </div>
                {phone ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xl font-semibold tabular-nums select-all">{phone}</span>
                    <Button type="button" variant="outline" size="sm" aria-label={`Copy phone for ${lead.name}`} onClick={() => copy(lead.id, phone)}>
                      {copied === lead.id ? <Check aria-hidden className="text-emerald-700" /> : <Copy aria-hidden />}
                      {copied === lead.id ? "Copied" : failed === lead.id ? "Copy failed, select the text" : "Copy"}
                    </Button>
                  </div>
                ) : (
                  <span className="text-sm text-muted-foreground">No phone</span>
                )}
                <div className="flex items-center gap-2">
                  {priority && <ToneBadge tone={priorityTone(lead.priority)}>{priority}</ToneBadge>}
                  <span className="text-sm tabular-nums text-muted-foreground">Fit {lead.fit_score ?? "n/a"}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p role="status" className="sr-only">
        {copied ? "Phone number copied" : failed ? "Copy failed, select the text" : ""}
      </p>
    </section>
  );
}
