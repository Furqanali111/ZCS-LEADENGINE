"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, getTeam, type TeamRange, type TeamRow } from "@/lib/api";
import { CRM_STATUSES } from "@/lib/constants";
import { PANEL_CLASS } from "@/lib/ui";

const STATUS_LABELS = Object.fromEntries(CRM_STATUSES.map((s) => [s.value, s.label]));

const RANGES: { id: TeamRange; label: string; empty: string }[] = [
  { id: "today", label: "Today", empty: "today" },
  { id: "yesterday", label: "Yesterday", empty: "yesterday" },
  { id: "24h", label: "Last 24 hours", empty: "in the last 24 hours" },
  { id: "48h", label: "Last 48 hours", empty: "in the last 48 hours" },
  { id: "7d", label: "Last 7 days", empty: "in the last 7 days" },
  { id: "30d", label: "Last 30 days", empty: "in the last 30 days" },
];

// "Today" comes with the dashboard stats (one round trip); the other windows are fetched when picked.
export function TeamActivity({ today }: { today: TeamRow[] }) {
  const [range, setRange] = useState<TeamRange>("today");
  const [fetched, setFetched] = useState<{ range: TeamRange; rows: TeamRow[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (range === "today") return;
    let stale = false;
    getTeam(range)
      .then((rows) => {
        if (stale) return;
        setFetched({ range, rows });
        setError(null);
      })
      .catch((e) => {
        if (!stale) setError(e instanceof ApiError ? e.message : "Could not load team activity.");
      });
    return () => {
      stale = true;
    };
  }, [range]);

  const rows = range === "today" ? today : fetched?.range === range ? fetched.rows : null;
  const current = RANGES.find((r) => r.id === range)!;

  return (
    <section aria-labelledby="team-activity" className={`${PANEL_CLASS} space-y-3`}>
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="team-activity" className="text-sm font-semibold">
          Team activity
        </h2>
        <div role="group" aria-label="Time period" className="ml-auto flex flex-wrap gap-1.5">
          {RANGES.map((r) => (
            <Button key={r.id} size="sm" variant={r.id === range ? "default" : "outline"} aria-pressed={r.id === range} onClick={() => setRange(r.id)}>
              {r.label}
            </Button>
          ))}
        </div>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div aria-live="polite">
        {rows === null ? (
          !error && <p className="text-sm text-muted-foreground">Loading...</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No calls, emails or status changes logged {current.empty}.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th scope="col" className="py-1 font-medium">Person</th>
                <th scope="col" className="py-1 text-right font-medium">Leads called</th>
                <th scope="col" className="py-1 text-right font-medium">Leads emailed</th>
                <th scope="col" className="py-1 text-right font-medium">Leads moved</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} className="border-t">
                  <th scope="row" className="py-1.5 text-left font-medium">
                    {r.name}
                    {r.changes.length > 0 && (
                      <span className="mt-1 flex flex-wrap gap-1 font-normal">
                        {r.changes.map((c) => (
                          <span key={`${c.from}-${c.to}`} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                            {c.from ? `${STATUS_LABELS[c.from] ?? c.from} to ` : "Set to "}
                            {c.to ? (STATUS_LABELS[c.to] ?? c.to) : "none"}
                            {c.count > 1 && ` x${c.count}`}
                          </span>
                        ))}
                      </span>
                    )}
                  </th>
                  <td className="py-1.5 text-right tabular-nums">{r.calls}</td>
                  <td className="py-1.5 text-right tabular-nums">{r.emails}</td>
                  <td className="py-1.5 text-right tabular-nums">{r.status_changes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="text-xs text-muted-foreground">Each lead counts once per person in the chosen period, however many times it was called or moved.</p>
    </section>
  );
}
