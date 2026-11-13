"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { CalendarClock, CheckCircle2, Handshake, RefreshCw, Sparkles, Star, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ToneBadge } from "@/components/tone-badge";
import { BarList } from "@/components/bar-list";
import { MyDay } from "@/components/my-day";
import { StatTile, StatTileSkeleton } from "@/components/stat-tile";
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

// Last stats per range, so the page paints at once and refreshes behind it. Read through useSyncExternalStore:
// the server snapshot is null, so prerender and hydration never see storage.
const cacheKey = (r: { from?: string; to?: string }) => `zcs-dashboard:${r.from ?? ""}:${r.to ?? ""}`;
const cacheListeners = new Set<() => void>();
const readCache = (key: string): string | null => {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
};
const writeCache = (key: string, s: DashboardStats) => {
  try {
    sessionStorage.setItem(key, JSON.stringify(s));
    cacheListeners.forEach((l) => l());
  } catch {
    /* storage full or blocked: the page just loads cold */
  }
};
const subscribeCache = (l: () => void) => {
  cacheListeners.add(l);
  return () => void cacheListeners.delete(l);
};
const REFRESH_MIN_MS = 30_000;

type Result = { key: string; tick: number; stats?: DashboardStats; error?: string };

export default function DashboardPage() {
  const [result, setResult] = useState<Result | null>(null);
  const [tick, setTick] = useState(0);
  const lastFetch = useRef(0);
  const [preset, setPreset] = useState<Preset>("all");
  const [applied, setApplied] = useState<{ from?: string; to?: string }>({ from: "2000-01-01" }); // no end date: the API uses today
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const key = cacheKey(applied);
  const cachedRaw = useSyncExternalStore(subscribeCache, () => readCache(key), () => null);
  const cached = useMemo<DashboardStats | null>(() => {
    try {
      return cachedRaw ? (JSON.parse(cachedRaw) as DashboardStats) : null;
    } catch {
      return null;
    }
  }, [cachedRaw]);
  const mine = result?.key === key ? result : null;
  const stats = mine?.stats ?? cached;
  const error = mine?.error ?? null;
  const loading = !mine || mine.tick !== tick; // derived from the request, so no state is set synchronously in the effect

  useEffect(() => {
    let live = true;
    lastFetch.current = Date.now();
    getDashboard(applied)
      .then((s) => {
        if (!live) return;
        writeCache(key, s);
        setResult({ key, tick, stats: s });
        setFrom((f) => f || s.range.from);
        setTo((t) => t || s.range.to);
      })
      .catch((e) => {
        if (!live) return;
        const error = e instanceof ApiError ? e.message : "Could not load the dashboard.";
        setResult((r) => ({ key, tick, error, stats: r?.key === key ? r.stats : undefined }));
      });
    return () => {
      live = false;
    };
  }, [applied, key, tick]);

  // Coming back to the tab refreshes the numbers, at most once per 30 s.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - lastFetch.current > REFRESH_MIN_MS) setTick((t) => t + 1);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

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
                setApplied(presetRange(p.id));
              }
            }}
            className={`rounded-full border px-4 py-1.5 text-sm font-medium transition-colors ${preset === p.id ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted"}`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-3">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => setTick((t) => t + 1)}>
          <RefreshCw aria-hidden className={`size-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
        <p role="status" className="text-sm text-muted-foreground">
          {loading ? (stats ? "Updating..." : "Loading dashboard...") : ""}
        </p>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {!stats && !error && (
        <dl aria-hidden className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <StatTileSkeleton key={i} />
          ))}
        </dl>
      )}
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

          <MyDay />
          <div className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 text-sm shadow-xs">
            <RefreshCw aria-hidden className="size-5 text-primary" />
            <span className="font-medium">Leads with a status change today</span>
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">{stats.status_changes_today}</span>
          </div>

          <section aria-labelledby="team-today" className={`${PANEL_CLASS} space-y-3`}>
            <h2 id="team-today" className="text-sm font-semibold">
              Team activity today
            </h2>
            {stats.team_today.length === 0 ? (
              <p className="text-sm text-muted-foreground">No calls, emails or status changes logged today yet.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th scope="col" className="py-1 font-medium">Person</th>
                    <th scope="col" className="py-1 text-right font-medium">Calls</th>
                    <th scope="col" className="py-1 text-right font-medium">Emails</th>
                    <th scope="col" className="py-1 text-right font-medium">Status changes</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.team_today.map((r) => (
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
            <p className="text-xs text-muted-foreground">Logged activity only, counted per UTC day.</p>
          </section>

          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatTile tone="blue" Icon={Users} label="Total leads" href="/leads" value={stats.total} hint="In the system" />
            <StatTile tone="green" Icon={Sparkles} label="New" href="/leads?crm_status=new" value={stats.new_leads} hint="Not contacted yet" />
            <StatTile tone="orange" Icon={Star} label="Critical and high priority" href="/leads?priority=critical" value={stats.critical_high} hint="Best fit first" />
            <StatTile tone="purple" Icon={Handshake} label="Meetings scheduled" href="/leads?crm_status=meeting_scheduled" value={stats.meetings_scheduled} hint="Booked" />
            <StatTile tone="teal" Icon={CheckCircle2} label="Converted" href="/leads?crm_status=converted" value={stats.converted} hint="Won" />
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

            <BarList title="Top states" items={stats.by_state} hrefFor={(k) => `/leads?state=${encodeURIComponent(k)}`} />
            <BarList title="Top specialties" items={stats.by_specialty} hrefFor={(k) => `/leads?specialty=${encodeURIComponent(k)}`} />
            <BarList title="By status" items={stats.by_status} labels={STATUS_LABELS} hrefFor={(k) => `/leads?crm_status=${encodeURIComponent(k)}`} />
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
