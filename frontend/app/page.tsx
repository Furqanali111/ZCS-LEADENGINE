"use client";

import { useEffect, useState } from "react";
import { BarList } from "@/components/bar-list";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, getDashboard, type DashboardStats } from "@/lib/api";
import { CRM_STATUSES, JOB_STATUS_LABELS } from "@/lib/constants";

const STATUS_LABELS = Object.fromEntries(CRM_STATUSES.map((s) => [s.value, s.label]));

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<{ from?: string; to?: string }>({});
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    let live = true;
    getDashboard(applied)
      .then((s) => {
        if (!live) return;
        setStats(s);
        setError(null);
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Could not load the dashboard."));
    return () => {
      live = false;
    };
  }, [applied]);

  const rangeInvalid = !!from && !!to && from > to;

  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">Dashboard</h1>
      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
      {!stats && !error && <p className="text-sm text-muted-foreground">Loading dashboard...</p>}
      {stats && (
        <>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <StatTile label="Total leads" value={stats.total} />
            <StatTile label="New" value={stats.new_leads} />
            <StatTile label="Critical and high priority" value={stats.critical_high} />
            <StatTile label="Follow-ups due" value={stats.follow_ups_due} />
            <StatTile label="Meetings scheduled" value={stats.meetings_scheduled} />
            <StatTile label="Converted" value={stats.converted} />
          </dl>

          <section aria-labelledby="conversion" className="space-y-3 rounded-lg border p-4">
            <h2 id="conversion" className="text-base font-semibold">
              Converted of contacted
            </h2>
            <p className="text-2xl font-semibold">
              {stats.conversion.converted} / {stats.conversion.contacted}
            </p>
            <p className="text-sm text-muted-foreground">
              {stats.conversion.rate === null
                ? "No contacts yet."
                : `${stats.conversion.converted} converted of ${stats.conversion.contacted} contacted (${Math.round(stats.conversion.rate * 100)}%), recorded outcomes only.`}{" "}
              Range: {stats.range.from} to {stats.range.to}.
            </p>
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (!rangeInvalid) setApplied({ from: from || undefined, to: to || undefined });
              }}
            >
              <div className="space-y-1">
                <Label htmlFor="range-from">From</Label>
                <Input id="range-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="range-to">To</Label>
                <Input id="range-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
              </div>
              <Button type="submit" variant="outline" disabled={rangeInvalid}>
                Apply range
              </Button>
              {rangeInvalid && (
                <p role="alert" className="text-sm text-red-700 dark:text-red-400">
                  From must not be after To.
                </p>
              )}
            </form>
          </section>

          <div className="grid gap-4 md:grid-cols-3">
            <BarList title="Top states" items={stats.by_state} />
            <BarList title="Top specialties" items={stats.by_specialty} />
            <BarList title="By status" items={stats.by_status} labels={STATUS_LABELS} />
          </div>

          <section aria-labelledby="recent-jobs">
            <h2 id="recent-jobs" className="mb-3 text-base font-semibold">
              Recent searches
            </h2>
            {stats.recent_jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No searches yet.</p>
            ) : (
              <ul className="space-y-2">
                {stats.recent_jobs.map((j) => (
                  <li key={j.id} className="flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm">
                    <span className="font-medium">
                      {j.specialty}, {j.city ? j.city + ", " : ""}
                      {j.state}
                    </span>
                    <Badge variant={j.status === "failed" ? "destructive" : "secondary"}>
                      {JOB_STATUS_LABELS[j.status] ?? j.status}
                    </Badge>
                    <span className="ml-auto text-muted-foreground">
                      {(j.counters.accepted_new ?? 0) + (j.counters.accepted_existing ?? 0)} of {j.target_count} leads
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
