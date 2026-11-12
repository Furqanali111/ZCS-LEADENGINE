"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, listLeads, type Lead } from "@/lib/api";
import { useName } from "@/lib/me";
import { PANEL_CLASS } from "@/lib/ui";

const STALE_DAYS = 7;

type Mine = { due: Lead[]; stale: Lead[] };

function LeadLink({ l, note }: { l: Lead; note: string }) {
  return (
    <li className="flex items-center justify-between gap-3 py-1.5">
      <Link href={`/leads/${l.id}`} className="min-w-0 truncate font-medium underline-offset-2 hover:underline">
        {l.name}
      </Link>
      <span className="shrink-0 text-xs text-muted-foreground">{note}</span>
    </li>
  );
}

// "My day": what this salesperson owes today. With no name set it shows the three first steps instead.
export function MyDay() {
  const me = useName();
  const [data, setData] = useState<{ me: string; mine?: Mine; error?: string } | null>(null);

  useEffect(() => {
    if (!me) return;
    let cancelled = false;
    Promise.all([
      listLeads({ owner: me, follow_up: "due", sort: "follow_up", order: "asc", page_size: 10 }),
      listLeads({ owner: me, crm_status: "in_progress", sort: "updated", order: "asc", page_size: 50 }),
    ])
      .then(([due, working]) => {
        if (cancelled) return;
        const cutoff = Date.now() - STALE_DAYS * 86_400_000;
        const stale = working.items.filter((l) => !l.last_contacted_at || new Date(l.last_contacted_at).getTime() < cutoff);
        setData({ me, mine: { due: due.items, stale } });
      })
      .catch((e) => !cancelled && setData({ me, error: e instanceof ApiError ? e.message : "Could not load your day." }));
    return () => {
      cancelled = true;
    };
  }, [me]);

  if (!me) {
    return (
      <section aria-labelledby="start-h" className={`${PANEL_CLASS} space-y-2`}>
        <h2 id="start-h" className="text-sm font-semibold">
          Start here
        </h2>
        <ol className="list-inside list-decimal space-y-1 text-sm text-muted-foreground">
          <li>Type your name in the box at the top right, so the team knows who is working which lead.</li>
          <li>Pick a lead from Call today below and press Claim this lead.</li>
          <li>Call, press the result (No answer, Spoke, Interested), and the next lead opens.</li>
        </ol>
      </section>
    );
  }

  const mine = data?.me === me ? data.mine : undefined;
  const error = data?.me === me ? data.error : undefined;
  return (
    <section aria-labelledby="myday-h" aria-busy={!mine && !error} className={`${PANEL_CLASS} space-y-3`}>
      <div className="flex items-center justify-between gap-3">
        <h2 id="myday-h" className="text-sm font-semibold">
          My day, {me}
        </h2>
        <Link href={`/leads?owner=${encodeURIComponent(me)}`} className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-muted">
          My leads
        </Link>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : !mine ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : mine.due.length === 0 && mine.stale.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing is due and none of your leads has gone quiet. Take the next one from Call today.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Follow-ups due ({mine.due.length})</h3>
            <ul className="divide-y text-sm">
              {mine.due.map((l) => (
                <LeadLink key={l.id} l={l} note={l.next_follow_up_at?.slice(0, 10) ?? ""} />
              ))}
              {mine.due.length === 0 && <li className="py-1.5 text-muted-foreground">None</li>}
            </ul>
          </div>
          <div>
            <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Quiet for {STALE_DAYS}+ days ({mine.stale.length})</h3>
            <ul className="divide-y text-sm">
              {mine.stale.slice(0, 10).map((l) => (
                <LeadLink key={l.id} l={l} note={l.last_contacted_at ? `last call ${l.last_contacted_at.slice(0, 10)}` : "never called"} />
              ))}
              {mine.stale.length === 0 && <li className="py-1.5 text-muted-foreground">None</li>}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
