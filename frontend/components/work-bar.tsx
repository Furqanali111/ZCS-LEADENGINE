"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Hand, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { addActivity, ApiError, claimLead, patchLead, releaseLead, type Lead } from "@/lib/api";
import { claimNext } from "@/lib/call-list";
import { useName } from "@/lib/me";
import { PANEL_CLASS } from "@/lib/ui";

// One-click call results. Each logs a call, sets the follow-up date and (where it applies) the sales status.
const QUICK = [
  { label: "No answer", outcome: "no_answer", summary: "Called, no answer", days: 2 },
  { label: "Spoke, call back", outcome: "spoke", summary: "Spoke, will call back", days: 3 },
  { label: "Interested", outcome: "interested", summary: "Spoke, interested", days: 2, status: "interested" },
  { label: "Not interested", outcome: "not_interested", summary: "Spoke, not interested", status: "not_interested" },
] as const;

function inDays(n: number) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

const errText = (e: unknown) => (e instanceof ApiError ? e.message : "Something went wrong.");

export function WorkBar({ lead, onChanged }: { lead: Lead; onChanged: () => void | Promise<void> }) {
  const me = useName();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; error: boolean } | null>(null);
  const mine = Boolean(me) && lead.owner?.toLowerCase() === me.toLowerCase();
  const theirs = Boolean(lead.owner) && !mine;

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setMsg({ text: "Saving...", error: false });
    try {
      await fn();
    } catch (e) {
      setMsg({ text: errText(e), error: true });
      await onChanged(); // someone may have claimed it first: show the real owner
    } finally {
      setBusy(false);
    }
  }

  async function goNext() {
    const next = await claimNext(me, lead.id);
    if (next) router.push(`/lead?id=${next.id}`);
    else setMsg({ text: "No more leads to call right now. New ones appear after a search.", error: false });
  }

  const quick = (q: (typeof QUICK)[number]) =>
    run(async () => {
      if (!lead.owner) await claimLead(lead.id);
      await addActivity(lead.id, {
        type: "call",
        occurred_at: new Date().toISOString(),
        summary: q.summary,
        outcome: q.outcome,
        ...("days" in q ? { next_follow_up_at: inDays(q.days) } : {}),
      });
      const status = "status" in q ? q.status : ["new", "in_progress", "researching"].includes(lead.crm_status) ? "called" : null;
      if (status) await patchLead(lead.id, { crm_status: status });
      setMsg({ text: `Saved: ${q.label}. Opening the next lead...`, error: false });
      await onChanged();
      await goNext();
    });

  return (
    <section aria-label="Work this lead" aria-busy={busy} className={`${PANEL_CLASS} flex flex-wrap items-center gap-x-6 gap-y-3 p-4`}>
      {!me ? (
        <p className="text-sm text-muted-foreground">Enter your name at the top right to claim leads and log results.</p>
      ) : theirs ? (
        <p className="flex items-center gap-2 text-sm font-medium text-tone-warning-fg">
          <Hand aria-hidden className="size-4" />
          {lead.owner} is working on this lead. Pick another one so you do not call the same office twice.
        </p>
      ) : mine ? (
        <>
          <p className="flex items-center gap-2 text-sm font-medium">
            <Hand aria-hidden className="size-4 text-primary" />
            You are working this lead
          </p>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await releaseLead(lead.id);
                await onChanged();
              })
            }
          >
            <Undo2 aria-hidden />
            Release
          </Button>
        </>
      ) : (
        <Button
          disabled={busy}
          onClick={() =>
            run(async () => {
              await claimLead(lead.id);
              await onChanged();
            })
          }
        >
          <Hand aria-hidden />
          Claim this lead
        </Button>
      )}

      {me && !theirs && (
        <div role="group" aria-label="Log the call result and go to the next lead" className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <span className="text-sm text-muted-foreground">Call result:</span>
          {QUICK.map((q) => (
            <Button key={q.label} variant="outline" disabled={busy} onClick={() => quick(q)}>
              {q.label}
            </Button>
          ))}
          <Button variant="secondary" disabled={busy} onClick={() => run(goNext)}>
            Skip to next lead
            <ArrowRight aria-hidden />
          </Button>
        </div>
      )}
      <p role={msg?.error ? "alert" : "status"} className={`basis-full text-sm empty:hidden ${msg?.error ? "text-destructive" : "text-muted-foreground"}`}>
        {msg?.text}
      </p>
    </section>
  );
}
