"use client";

import { useEffect, useState } from "react";
import { CalendarClock, CheckCircle2, Handshake, Sparkles, Star, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ToneBadge } from "@/components/tone-badge";
import { BarList } from "@/components/bar-list";
import { StatTile } from "@/components/stat-tile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, getDashboard, type DashboardStats } from "@/lib/api";
import { PANEL_CLASS } from "@/lib/ui";
import { CRM_STATUSES, JOB_STATUS_LABELS } from "@/lib/constants";

const STATUS_LABELS = Object.fromEntries(CRM_STATUSES.map((s) => [s.value, s.label]));

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState<{ from?: string; to?: string }>({});
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    getDashboard(applied)
      .then((s) => {
        if (!live) return;
        setStats(s);
        setError(null);
        setLoading(false);
        setFrom((f) => f || s.range.from);
        setTo((t) => t || s.range.to);
      })
      .catch((e) => {
        if (!live) return;
        setError(e instanceof ApiError ? e.message : "Could not load the dashboard.");
        setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [applied]);

  const rangeInvalid = !!from && !!to && from > to;

  return (
    <div className="space-y-6" aria-busy={loading}>
      <PageHeader title="Dashboard" description="Where the pipeline stands today." />
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {loading && <p className="text-sm text-muted-foreground">Updating...</p>}
      {!stats && !error && <p className="text-sm text-muted-foreground">Loading dashboard...</p>}
      {stats && (
        <>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <StatTile Icon={Users} label="Total leads" value={stats.total} />
            <StatTile Icon={Sparkles} label="New" value={stats.new_leads} />
            <StatTile Icon={Star} label="Critical and high priority" value={stats.critical_high} />
            <StatTile Icon={CalendarClock} label="Follow-ups due" value={stats.follow_ups_due} />
            <StatTile Icon={Handshake} label="Meetings scheduled" value={stats.meetings_scheduled} />
            <StatTile Icon={CheckCircle2} label="Converted" value={stats.converted} />
          </dl>

          <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-4">
          <section aria-labelledby="conversion" className={`${PANEL_CLASS} space-y-3`}>
            <h2 id="conversion" className="text-sm font-semibold">
              Converted of contacted
            </h2>
            <p className="text-3xl font-semibold tracking-tight tabular-nums">
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
                if (rangeInvalid) return;
                setLoading(true);
                setApplied({ from: from || undefined, to: to || undefined });
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
                <p role="alert" className="text-sm text-destructive">
                  From must not be after To.
                </p>
              )}
            </form>
          </section>

            <BarList title="Top states" items={stats.by_state} />
            <BarList title="Top specialties" items={stats.by_specialty} />
            <BarList title="By status" items={stats.by_status} labels={STATUS_LABELS} />
          </div>

          <section aria-labelledby="recent-jobs">
            <h2 id="recent-jobs" className="mb-3 text-sm font-semibold">
              Recent searches
            </h2>
            {stats.recent_jobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No searches yet.</p>
            ) : (
              <ul className="grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
                {stats.recent_jobs.map((j) => (
                  <li key={j.id} className={`${PANEL_CLASS} flex flex-wrap items-center gap-3 py-3 text-sm`}>
                    <span className="font-medium">
                      {j.specialty}, {j.city ? j.city + ", " : ""}
                      {j.state}
                    </span>
                    <ToneBadge tone={j.status === "failed" ? "danger" : j.status === "completed" ? "success" : j.status === "paused" ? "warning" : "neutral"}>
                      {JOB_STATUS_LABELS[j.status] ?? j.status}
                    </ToneBadge>
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
