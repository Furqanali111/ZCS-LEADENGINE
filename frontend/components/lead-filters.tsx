"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listJobs, type Job, type LeadFilters } from "@/lib/api";
import { CRM_STATUSES, ORG_TYPES, PRIORITIES, SPECIALTIES, US_STATES } from "@/lib/constants";

const SELECT =
  "mt-1 h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

function jobLabel(j: Job) {
  return `${j.specialty}, ${j.city ? j.city + ", " : ""}${j.state} (${new Date(j.created_at).toLocaleDateString()})`;
}

export function LeadFilters({
  filters,
  onChange,
  onClear,
}: {
  filters: LeadFilters;
  onChange: (changes: Record<string, string | undefined>) => void;
  onClear: () => void;
}) {
  // Text boxes keep a local value so typing is instant; the URL (and the fetch) follow 300 ms after the last keystroke.
  const [q, setQ] = useState(filters.q ?? "");
  const [specialty, setSpecialty] = useState(filters.specialty ?? "");
  const [minScore, setMinScore] = useState(filters.min_score !== undefined ? String(filters.min_score) : "");
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  useEffect(() => {
    const t = timers.current;
    return () => Object.values(t).forEach(clearTimeout);
  }, []);
  const debounced = (key: string, value: string) => {
    clearTimeout(timers.current[key]);
    timers.current[key] = setTimeout(() => onChange({ [key]: value.trim() || undefined }), 300);
  };

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobsError, setJobsError] = useState(false);
  useEffect(() => {
    listJobs()
      .then(setJobs)
      .catch(() => setJobsError(true));
  }, []);

  const select = (id: string, label: string, key: keyof LeadFilters, options: { value: string; label: string }[]) => (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <select id={id} className={SELECT} value={String(filters[key] ?? "")} onChange={(e) => onChange({ [key]: e.target.value || undefined })}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <form role="search" aria-label="Filter leads" onSubmit={(e) => e.preventDefault()} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div>
        <Label htmlFor="f-q">Search name or city</Label>
        <Input
          id="f-q"
          type="search"
          className="mt-1"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            debounced("q", e.target.value);
          }}
        />
      </div>
      {select("f-state", "State", "state", US_STATES.map((s) => ({ value: s.code, label: `${s.name} (${s.code})` })))}
      <div>
        <Label htmlFor="f-specialty">Specialty</Label>
        <Input
          id="f-specialty"
          className="mt-1"
          list="f-specialty-options"
          value={specialty}
          onChange={(e) => {
            setSpecialty(e.target.value);
            debounced("specialty", e.target.value);
          }}
        />
        <datalist id="f-specialty-options">
          {SPECIALTIES.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      </div>
      {select("f-org", "Organization type", "organization_type", ORG_TYPES)}
      {select("f-priority", "Priority", "priority", PRIORITIES)}
      <div>
        <Label htmlFor="f-min">Minimum score (0 to 100)</Label>
        <Input
          id="f-min"
          type="number"
          min={0}
          max={100}
          className="mt-1"
          value={minScore}
          onChange={(e) => {
            setMinScore(e.target.value);
            debounced("min_score", e.target.value);
          }}
        />
      </div>
      {select("f-status", "Sales status", "crm_status", CRM_STATUSES)}
      <div>
        <Label htmlFor="f-job">Search job</Label>
        <select id="f-job" className={SELECT} value={filters.search_job_id ?? ""} onChange={(e) => onChange({ search_job_id: e.target.value || undefined })}>
          <option value="">All</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>
              {jobLabel(j)}
            </option>
          ))}
        </select>
        {jobsError && <p className="mt-1 text-xs text-muted-foreground">Search jobs could not be loaded.</p>}
      </div>
      <div className="sm:col-span-2 lg:col-span-4">
        <Button type="button" variant="outline" size="sm" onClick={() => {
            Object.values(timers.current).forEach(clearTimeout);
            setQ("");
            setSpecialty("");
            setMinScore("");
            onClear();
          }}>
          Clear filters
        </Button>
      </div>
    </form>
  );
}
