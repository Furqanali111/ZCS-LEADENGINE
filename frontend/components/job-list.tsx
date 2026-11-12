"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ToneBadge, type Tone } from "@/components/tone-badge";
import { PANEL_CLASS } from "@/lib/ui";
import { ApiError, cancelJob, listJobs, resumeJob, type Job } from "@/lib/api";
import { JOB_STATUS_LABELS } from "@/lib/constants";

const ACTIVE = ["queued", "running"];
const JOB_TONE: Record<string, Tone> = { queued: "neutral", running: "info", paused: "warning", completed: "success", cancelled: "neutral", failed: "danger" };

// Bar colour follows the status tone instead of the heavy primary color.
const BAR: Record<Tone, string> = {
  danger: "[&_[data-slot=progress-indicator]]:bg-tone-danger-fg",
  warning: "[&_[data-slot=progress-indicator]]:bg-tone-warning-fg",
  success: "[&_[data-slot=progress-indicator]]:bg-tone-success-fg",
  info: "[&_[data-slot=progress-indicator]]:bg-tone-info-fg",
  neutral: "[&_[data-slot=progress-indicator]]:bg-muted-foreground",
};

const COUNTER_LABELS:[keyof Job["counters"], string][] = [
  ["candidates_seen", "Records checked"],
  ["accepted_new", "New leads"],
  ["accepted_existing", "Already known"],
  ["skipped_excluded", "Skipped by filters"],
  ["skipped_inactive", "Skipped, inactive"],
  ["skipped_not_sole_proprietor", "Skipped, not sole proprietor"],
  ["skipped_works_at_known_org", "Skipped, works at known practice"],
  ["pages_fetched", "Pages fetched"],
  ["source_failures", "Source failures"],
];

const ENRICH_LABELS: [keyof Job["counters"], string][] = [
  ["websites_found", "Websites found"],
  ["emails_found", "Emails found"],
  ["people_found", "People found"],
  ["no_website_found", "No website"],
  ["skipped", "Pages skipped"],
];

function summary(j: Job) {
  const types = [j.include_practices && "practices", j.include_solo && "solo doctors"].filter(Boolean).join(" + ");
  if (!types) return `${j.specialty}, ${j.state}`; // an "enrich existing leads" job has no search phases
  return `${j.specialty}, ${j.city ? j.city + ", " : ""}${j.state} (${types})`;
}

export function JobList({ refreshKey }: { refreshKey: number }) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setJobs(await listJobs());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load searches.");
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0); // async so state is not set synchronously in the effect
    return () => clearTimeout(t);
  }, [load, refreshKey]);

  const anyActive = jobs?.some((j) => ACTIVE.includes(j.status)) ?? false;
  useEffect(() => {
    if (!anyActive) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [anyActive, load]);

  async function act(fn: (id: string) => Promise<Job>, id: string) {
    try {
      await fn(id);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed.");
    }
    load();
  }

  if (jobs === null && !error) return <p className="text-sm text-muted-foreground">Loading searches...</p>;

  return (
    <div className="space-y-4">
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div aria-live="polite">
        {jobs?.length === 0 && <p className="text-sm text-muted-foreground">No searches yet.</p>}
      </div>
      <ul className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
        {jobs?.map((j) => {
          const done = (j.counters.accepted_new ?? 0) + (j.counters.accepted_existing ?? 0);
          const found = j.counters.accepted_new ?? 0;
          const canView = j.status === "completed" || ((j.status === "paused" || j.status === "failed") && found > 0);
          const pct = Math.min(100, Math.round((done / j.target_count) * 100));
          return (
            <li key={j.id} className={`${PANEL_CLASS} space-y-2.5`}>
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-medium">{summary(j)}</span>
                <ToneBadge tone={JOB_TONE[j.status] ?? "neutral"}>{JOB_STATUS_LABELS[j.status] ?? j.status}</ToneBadge>
                <span className="ml-auto flex gap-2">
                  {ACTIVE.includes(j.status) && (
                    <Button variant="outline" size="sm" onClick={() => act(cancelJob, j.id)}>
                      Cancel
                    </Button>
                  )}
                  {canView && (
                    <Link href={`/leads?search_job_id=${j.id}`} className={buttonVariants({ size: "sm" })}>
                      View leads
                    </Link>
                  )}
                  {(j.status === "paused" || j.status === "failed") && (
                    <Button variant="outline" size="sm" onClick={() => act(resumeJob, j.id)}>
                      Resume
                    </Button>
                  )}
                </span>
              </div>
              <Progress value={pct} aria-label={`Progress for ${summary(j)}`} className={`[&_[data-slot=progress-track]]:h-1.5 ${BAR[JOB_TONE[j.status] ?? "neutral"]}`} />
              <p className="text-sm">
                {j.include_practices || j.include_solo
                  ? `${found} new ${found === 1 ? "lead" : "leads"} found (target ${j.target_count})`
                  : `${j.counters.websites_found ?? 0} websites and ${j.counters.emails_found ?? 0} emails found for ${j.counters.enrich_attempted ?? 0} leads`}
              </p>
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer">Details</summary>
              <dl className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
                {COUNTER_LABELS.map(([k, label]) => (
                  <div key={k} className="flex gap-1">
                    <dt>{label}:</dt>
                    <dd className="tabular-nums">{j.counters[k] ?? 0}</dd>
                  </div>
                ))}
              </dl>
              {j.enrich && (
                <dl aria-label="Enrichment results" className="mt-2 flex flex-wrap gap-x-5 gap-y-1 border-t pt-2">
                  {ENRICH_LABELS.map(([k, label]) => (
                    <div key={k} className="flex gap-1">
                      <dt>{label}:</dt>
                      <dd className="tabular-nums">{j.counters[k] ?? 0}</dd>
                    </div>
                  ))}
                </dl>
              )}
              </details>
              {j.error && (
                <p role={j.status === "paused" ? "status" : undefined} className="text-sm text-destructive">
                  {j.status === "paused" ? `Paused: ${j.error} Resume when fixed.` : `Error: ${j.error}`}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
