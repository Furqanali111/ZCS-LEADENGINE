"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { addActivity, ApiError } from "@/lib/api";
import { ACTIVITY_TYPES, OUTCOMES } from "@/lib/constants";

const SELECT =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

// Local time for datetime-local inputs (not UTC).
function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

// Status changes are written by the server, so they are not offered here.
const TYPES = ACTIVITY_TYPES.filter((t) => t.value !== "status_change");

export function ActivityForm({ leadId, onSaved }: { leadId: string; onSaved: () => void }) {
  const [type, setType] = useState("call");
  const [when, setWhen] = useState(nowLocal);
  const [summary, setSummary] = useState("");
  const [outcome, setOutcome] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});
    try {
      await addActivity(leadId, {
        type,
        occurred_at: new Date(when).toISOString(),
        summary: summary.trim(),
        outcome: outcome || null,
        next_follow_up_at: followUp || null,
      });
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
    <form onSubmit={submit} aria-label="Log an activity" className="space-y-3 rounded-lg border p-4">
      <h2 className="text-sm font-semibold">Log an activity</h2>
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
          required
          maxLength={2000}
          rows={3}
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          aria-invalid={fields.summary ? true : undefined}
          aria-describedby={fields.summary ? "act-summary-err" : undefined}
          className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive dark:bg-input/30"
        />
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
        <p role="alert" className="text-sm text-destructive">
          {error ? `Not saved. ${error}` : ""}
        </p>
      </div>
    </form>
  );
}
