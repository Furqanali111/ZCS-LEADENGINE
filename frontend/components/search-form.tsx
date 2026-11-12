"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, createSearch, getSources, type Source } from "@/lib/api";
import { SOURCE_STATUS_LABELS, SPECIALTIES, US_STATES } from "@/lib/constants";

function CheckRow({
  label,
  checked,
  onChange,
  disabled,
  hint,
  describedBy,
}: {
  label: string;
  checked: boolean;
  onChange?: (v: boolean) => void;
  disabled?: boolean;
  hint?: string;
  describedBy?: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <Checkbox checked={checked} disabled={disabled} aria-describedby={describedBy} onCheckedChange={(v) => onChange?.(v)} />
      <span className={disabled ? "text-muted-foreground" : undefined}>{label}</span>
      {hint && <span className="text-muted-foreground">({hint})</span>}
    </label>
  );
}

function FieldError({ id, text }: { id: string; text?: string }) {
  return text ? (
    <p id={id} className="mt-1 text-sm text-red-700 dark:text-red-400">
      {text}
    </p>
  ) : null;
}

export function SearchForm({ onCreated }: { onCreated: () => void }) {
  const [specialty, setSpecialty] = useState("Internal Medicine");
  const [state, setState] = useState("");
  const [city, setCity] = useState("");
  const [target, setTarget] = useState("500");
  const [practices, setPractices] = useState(true);
  const [solo, setSolo] = useState(true);
  const [subparts, setSubparts] = useState(true);
  const [hospitals, setHospitals] = useState(false);
  const [enrich, setEnrich] = useState(false);
  const [sources, setSources] = useState<Source[] | null>(null);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    getSources()
      .then((list) => {
        setSources(list);
        setSelected(list.filter((s) => s.key === "npi_registry" && s.status === "available").map((s) => s.key));
      })
      .catch((e: Error) => setSourcesError(e.message));
  }, []);

  const targetNum = Number(target);
  const targetValid = Number.isInteger(targetNum) && targetNum >= 1 && targetNum <= 1200;
  const canSubmit =
    !submitting && (practices || solo) && selected.length > 0 && targetValid && specialty.trim() !== "" && state !== "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await createSearch({
        specialty: specialty.trim(),
        state,
        city: city.trim() || null,
        target_count: targetNum,
        include_practices: practices,
        include_solo: solo,
        include_subparts: subparts,
        include_hospitals: hospitals,
        sources: selected,
        ...(enrich && !enrichReason && { enrich: true }),
      });
      onCreated();
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fields);
        setFormError(err.message);
      } else {
        setFormError("Something went wrong. Try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const searchProviders = sources?.filter((s) => s.key === "brave_search" || s.key === "tavily_search") ?? [];
  const websites = sources?.find((s) => s.key === "practice_websites");
  const usableProvider = searchProviders.some((s) => s.status === "available" && !s.key_missing);
  const enrichReason =
    sources === null
      ? null
      : !usableProvider
        ? "No search provider is ready: set TAVILY_API_KEY (or BRAVE_API_KEY) in backend/.env and mark the provider available (see README)."
        : websites?.status !== "available"
          ? "Practice websites is not marked available yet (see README)."
          : null;
  const visibleSources = sources?.filter((s) => s.status !== "rejected") ?? [];

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="specialty">Specialty</Label>
          <Input
            id="specialty"
            list="specialty-options"
            value={specialty}
            maxLength={100}
            required
            aria-invalid={!!fieldErrors.specialty}
            aria-describedby="specialty-error"
            onChange={(e) => setSpecialty(e.target.value)}
            className="mt-1"
          />
          <datalist id="specialty-options">
            {SPECIALTIES.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
          <FieldError id="specialty-error" text={fieldErrors.specialty} />
        </div>
        <div>
          <Label htmlFor="state">State</Label>
          <select
            id="state"
            value={state}
            required
            aria-invalid={!!fieldErrors.state}
            aria-describedby="state-error"
            onChange={(e) => setState(e.target.value)}
            className="mt-1 h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          >
            <option value="">Select a state</option>
            {US_STATES.map((s) => (
              <option key={s.code} value={s.code}>
                {s.name} ({s.code})
              </option>
            ))}
          </select>
          <FieldError id="state-error" text={fieldErrors.state} />
        </div>
        <div>
          <Label htmlFor="city">City (optional)</Label>
          <Input
            id="city"
            value={city}
            maxLength={100}
            aria-invalid={!!fieldErrors.city}
            aria-describedby="city-error"
            onChange={(e) => setCity(e.target.value)}
            className="mt-1"
          />
          <FieldError id="city-error" text={fieldErrors.city} />
        </div>
        <div>
          <Label htmlFor="target">Target count</Label>
          <Input
            id="target"
            type="number"
            min={1}
            max={1200}
            value={target}
            aria-invalid={!targetValid || !!fieldErrors.target_count}
            aria-describedby="target-help target-error"
            onChange={(e) => setTarget(e.target.value)}
            className="mt-1"
          />
          <p id="target-help" className="mt-1 text-sm text-muted-foreground">
            One search returns at most 1,200 records. For large states, add a city.
          </p>
          <FieldError
            id="target-error"
            text={fieldErrors.target_count ?? (targetValid ? undefined : "Enter a whole number from 1 to 1200.")}
          />
        </div>
      </div>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium">Lead types</legend>
        <CheckRow label="Practices" checked={practices} onChange={setPractices} />
        <CheckRow label="Solo doctors" checked={solo} onChange={setSolo} />
        {!practices && !solo && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            Select at least one lead type.
          </p>
        )}
        <CheckRow label="Include hospital and health-system subparts" checked={subparts} onChange={setSubparts} />
        <CheckRow label="Include hospitals" checked={hospitals} onChange={setHospitals} />
      </fieldset>

      <fieldset className="space-y-2" aria-describedby="sources-error">
        <legend className="mb-1 text-sm font-medium">Sources</legend>
        {sources === null && !sourcesError && <p className="text-sm text-muted-foreground">Loading sources...</p>}
        {sourcesError && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            Could not load sources: {sourcesError}
          </p>
        )}
        {visibleSources.map((s) =>
          s.status === "available" ? (
            <CheckRow
              key={s.key}
              label={s.name}
              checked={selected.includes(s.key)}
              onChange={(v) => setSelected((cur) => (v ? [...cur, s.key] : cur.filter((k) => k !== s.key)))}
            />
          ) : (
            <CheckRow
              key={s.key}
              label={s.name}
              checked={false}
              disabled
              hint={SOURCE_STATUS_LABELS[s.status] ?? s.status}
            />
          ),
        )}
        <FieldError id="sources-error" text={fieldErrors.sources} />
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium">Enrichment</legend>
        <CheckRow label="Also find websites and emails" checked={enrich && !enrichReason} onChange={setEnrich} disabled={!!enrichReason} describedBy="enrich-hint" />
        <p id="enrich-hint" className="text-sm text-muted-foreground">
          {enrichReason ? `Unavailable: ${enrichReason} ` : ""}Uses your search API key, one query per lead
          {targetValid ? `, so about ${targetNum} ${targetNum === 1 ? "query" : "queries"} for this search` : ""}.
        </p>
      </fieldset>

      {formError && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {formError}
        </p>
      )}
      <Button type="submit" disabled={!canSubmit}>
        {submitting ? "Starting..." : "Start search"}
      </Button>
    </form>
  );
}
