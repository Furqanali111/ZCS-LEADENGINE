"use client";

import { useEffect, useRef, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SELECT_CLASS } from "@/lib/ui";
import { listJobs, listOwners, type Job, type LeadFilters } from "@/lib/api";
import { useName } from "@/lib/me";
import { CRM_STATUSES, ORG_TYPES, PRIORITIES, SPECIALTIES, US_STATES } from "@/lib/constants";

const SELECT = `mt-1 ${SELECT_CLASS}`;

const FOLLOW_UP_OPTIONS = [
  { value: "due", label: "Due (today or earlier)" },
  { value: "overdue", label: "Overdue (before today)" },
  { value: "none", label: "No follow-up date" },
];

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
  // Follow the URL on back/forward: when the URL value changes to something other than what is typed, adopt it.
  const urlQ = filters.q ?? "";
  const urlSpecialty = filters.specialty ?? "";
  const urlMin = filters.min_score !== undefined ? String(filters.min_score) : "";
  const [seen, setSeen] = useState({ urlQ, urlSpecialty, urlMin });
  if (seen.urlQ !== urlQ || seen.urlSpecialty !== urlSpecialty || seen.urlMin !== urlMin) {
    setSeen({ urlQ, urlSpecialty, urlMin });
    if (q.trim() !== urlQ) setQ(urlQ);
    if (specialty.trim() !== urlSpecialty) setSpecialty(urlSpecialty);
    if (minScore.trim() !== urlMin) setMinScore(urlMin);
  }

  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });
  useEffect(() => {
    const t = timers.current;
    return () => Object.values(t).forEach(clearTimeout);
  }, []);
  const debounced = (key: string, value: string) => {
    clearTimeout(timers.current[key]);
    timers.current[key] = setTimeout(() => onChangeRef.current({ [key]: value.trim() || undefined }), 300);
  };

  const [more, setMore] = useState(() =>
    Boolean(filters.specialty || filters.organization_type || filters.min_score !== undefined || filters.follow_up || filters.search_job_id || filters.has_website || filters.has_email),
  );
  const me = useName();
  const [owners, setOwners] = useState<string[]>([]);
  useEffect(() => {
    listOwners().then(setOwners).catch(() => {});
  }, []);
  const ownerOptions = [
    ...(me ? [{ value: me, label: "Mine" }] : []),
    { value: "none", label: "Unclaimed" },
    ...owners.filter((o) => o.toLowerCase() !== me.toLowerCase()).map((o) => ({ value: o, label: o })),
  ];
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
    <form role="search" aria-label="Filter leads" onSubmit={(e) => e.preventDefault()} className="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] items-end gap-x-3 gap-y-2.5 rounded-xl border bg-card p-3 shadow-xs [&_label]:text-xs [&_label]:text-muted-foreground">
      <div className="col-span-full sm:col-span-2">
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
      {select("f-priority", "Priority", "priority", PRIORITIES)}
      {select("f-status", "Sales status", "crm_status", CRM_STATUSES)}
      {select("f-owner", "Owner", "owner", ownerOptions)}
      <div className="flex items-end justify-end gap-2 sm:col-span-2">
        <Button type="button" variant="ghost" size="sm" aria-expanded={more} aria-controls="more-filters" onClick={() => setMore((m) => !m)}>
          {more ? "Fewer filters" : "More filters"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            Object.values(timers.current).forEach(clearTimeout);
            setQ("");
            setSpecialty("");
            setMinScore("");
            onClear();
          }}
        >
          Clear filters
        </Button>
      </div>
      {more && (
        <div id="more-filters" className="col-span-full grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] items-end gap-x-3 gap-y-2.5 border-t pt-3">
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
      {select("f-follow", "Follow-up", "follow_up", FOLLOW_UP_OPTIONS)}
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
      <fieldset className="flex h-8 items-center gap-4">
        <legend className="sr-only">Enrichment</legend>
        {([["has_website", "Has website"], ["has_email", "Has email"]] as const).map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm! whitespace-nowrap text-foreground!">
            <Checkbox checked={filters[key] === "true"} onCheckedChange={(v) => onChange({ [key]: v ? "true" : undefined })} />
            {label}
          </label>
        ))}
      </fieldset>
        </div>
      )}
    </form>
  );
}
