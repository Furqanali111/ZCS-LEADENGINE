"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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

type Preset = "all" | "week" | "month" | "last-month" | "custom";
const PRESETS: { id: Preset; label: string }[] = [
  { id: "all", label: "All time" },
  { id: "week", label: "This week" },
  { id: "month", label: "This month" },
  { id: "last-month", label: "Last month" },
  { id: "custom", label: "Custom" },
];

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function presetRange(p: Exclude<Preset, "custom">): { from: string; to: string } {
  const now = new Date();
  if (p === "all") return { from: "2000-01-01", to: ymd(now) };
  if (p === "week") return { from: ymd(new Date(now.getFullYear(), now.getMonth(), now.getDate() - ((now.getDay() + 6) % 7))), to: ymd(now) };
  if (p === "month") return { from: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), to: ymd(now) };
  return { from: ymd(new Date(now.getFullYear(), now.getMonth() - 1, 1)), to: ymd(new Date(now.getFullYear(), now.getMonth(), 0)) };
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preset, setPreset] = useState<Preset>("all");
  const [applied, setApplied] = useState<{ from?: string; to?: string }>({ from: "2000-01-01" }); // no end date: the API uses today
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
      <div role="group" aria-label="Time range" className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            aria-pressed={preset === p.id}
            onClick={() => {
              setPreset(p.id);
              if (p.id !== "custom") {
                setLoading(true);
                setApplied(presetRange(p.id));
              }
            }}
            className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-colors ${preset === p.id ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted"}`}
          >
            {p.label}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {loading && <p className="text-sm text-muted-foreground">Updating...</p>}
      {!stats && !error && <p className="text-sm text-muted-foreground">Loading dashboard...</p>}
      {stats && (
        <>
          <Link
            href="/leads?follow_up=due"
            className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 text-sm shadow-xs hover:bg-muted"
          >
            <CalendarClock aria-hidden className="size-5 text-orange-700 dark:text-orange-400" />
            <span className="font-medium">Follow-ups due</span>
            <span className="rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-semibold text-orange-900">{stats.follow_ups_due}</span>
            <span className="ml-auto text-muted-foreground">{stats.follow_ups_due === 0 ? "Nothing due today" : "Open the list"}</span>
          </Link>

          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatTile tone="blue" Icon={Users} label="Total leads" value={stats.total} hint="In the system" />
            <StatTile tone="green" Icon={Sparkles} label="New" value={stats.new_leads} hint="Not contacted yet" />
            <StatTile tone="orange" Icon={Star} label="Critical and high priority" value={stats.critical_high} hint="Best fit first" />
            <StatTile tone="purple" Icon={Handshake} label="Meetings scheduled" value={stats.meetings_scheduled} hint="Booked" />
            <StatTile tone="teal" Icon={CheckCircle2} label="Converted" value={stats.converted} hint="Won" />
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
            {preset === "custom" && (
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
            )}
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
