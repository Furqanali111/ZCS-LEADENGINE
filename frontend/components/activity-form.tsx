"use client";

import { useImperativeHandle, useRef, useState, type Ref } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { addActivity, ApiError } from "@/lib/api";
import { PANEL_CLASS, SELECT_CLASS, TEXTAREA_CLASS } from "@/lib/ui";
import { ACTIVITY_TYPES, OUTCOMES } from "@/lib/constants";

const SELECT = SELECT_CLASS;

// Local time for datetime-local inputs (not UTC).
function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

// Status changes are written by the server, so they are not offered here.
const TYPES = ACTIVITY_TYPES.filter((t) => t.value !== "status_change");

export type ActivityFormHandle = { logCall: () => void };

// One "Activity" card: the log form on top, the timeline (children) below.
export function ActivityForm({
  leadId,
  onSaved,
  handle,
  children,
}: {
  leadId: string;
  onSaved: () => void;
  handle?: Ref<ActivityFormHandle>;
  children?: React.ReactNode;
}) {
  const card = useRef<HTMLElement>(null);
  const summaryEl = useRef<HTMLTextAreaElement>(null);
  const [type, setType] = useState("call");
  const [when, setWhen] = useState(nowLocal);
  const [summary, setSummary] = useState("");
  const [outcome, setOutcome] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});

  useImperativeHandle(handle, () => ({
    logCall() {
      setType("call");
      card.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
      summaryEl.current?.focus({ preventScroll: true });
    },
  }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    setFields({});
    try {
      await addActivity(leadId, {
        type,
        occurred_at: new Date(when).toISOString(),
        summary: summary.trim(),
        outcome: outcome || null,
        // Omit the key when empty: the backend treats a present key (even null) as "set it".
        ...(followUp ? { next_follow_up_at: followUp } : {}),
      });
      setSaved(true);
      // Typed text is cleared only after the server accepted it.
      setSummary("");
      setOutcome("");
      setFollowUp("");
      setWhen(nowLocal());
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unknown error.");
      if (err instanceof ApiError) setFields(err.fields);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section ref={card} aria-labelledby="activity-h" className={`${PANEL_CLASS} scroll-mt-4 space-y-4`}>
      <h2 id="activity-h" className="text-sm font-semibold">
        Activity
      </h2>
      <form onSubmit={submit} aria-label="Log an activity" className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="act-type">Type</Label>
          <select id="act-type" className={SELECT} value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="act-when">Date and time</Label>
          <Input id="act-when" type="datetime-local" required value={when} onChange={(e) => setWhen(e.target.value)} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="act-summary">Summary</Label>
        <textarea
          id="act-summary"
          ref={summaryEl}
          required
          maxLength={2000}
          rows={3}
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          aria-invalid={fields.summary ? true : undefined}
          aria-describedby={fields.summary ? "act-summary-hint act-summary-err" : "act-summary-hint"}
          className={TEXTAREA_CLASS}
        />
        <p id="act-summary-hint" className="text-xs text-muted-foreground">
          Business notes only. No patient information.
        </p>
        {fields.summary && (
          <p id="act-summary-err" className="text-sm text-destructive">
            {fields.summary}
          </p>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="act-outcome">Outcome (optional)</Label>
          <select id="act-outcome" className={SELECT} value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="">None</option>
            {OUTCOMES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="act-follow">Next follow-up (optional)</Label>
          <Input id="act-follow" type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving..." : "Add to timeline"}
        </Button>
        <p role="status" className="text-sm">
          {saved ? "Activity saved" : ""}
        </p>
        <p role="alert" className="text-sm text-destructive">
          {error ? `Not saved. ${error}` : ""}
        </p>
      </div>
      </form>
      <div className="border-t pt-4">{children}</div>
    </section>
  );
}
