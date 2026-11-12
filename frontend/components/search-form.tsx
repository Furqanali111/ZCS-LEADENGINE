"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SavedSearches } from "@/components/saved-searches";
import {
  ApiError,
  createSavedSearch,
  createSearch,
  getSearchProgress,
  getSources,
  resetSearchProgress,
  touchSavedSearch,
  type SavedSearch,
  type SearchProgress,
  type Source,
} from "@/lib/api";
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

const OTHER = "__other";
const SELECT_CLASS =
  "mt-1 h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

function FieldError({ id, text }: { id: string; text?: string }) {
  return text ? (
    <p id={id} className="mt-1 text-sm text-red-700 dark:text-red-400">
      {text}
    </p>
  ) : null;
}

// aria-describedby lists only ids that exist in the DOM
const describe = (...ids: (string | false | undefined)[]) => ids.filter(Boolean).join(" ") || undefined;

export function SearchForm({ onCreated }: { onCreated: () => void }) {
  const [choice, setChoice] = useState<string>("Internal Medicine");
  const [custom, setCustom] = useState("");
  const specialty = choice === OTHER ? custom : choice;
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
  const [progress, setProgress] = useState<SearchProgress | null>(null);
  const [savedKey, setSavedKey] = useState(0);
  const [usedSavedId, setUsedSavedId] = useState<string | null>(null);
  const [saveName, setSaveName] = useState("");
  const [saveMsg, setSaveMsg] = useState<{ text: string; error: boolean } | null>(null);

  function applySaved(s: SavedSearch) {
    const known = (SPECIALTIES as readonly string[]).includes(s.specialty);
    setChoice(known ? s.specialty : OTHER);
    setCustom(known ? "" : s.specialty);
    setState(s.state);
    setCity(s.city ?? "");
    setTarget(String(s.target_count));
    setPractices(s.include_practices);
    setSolo(s.include_solo);
    setSubparts(s.include_subparts);
    setHospitals(s.include_hospitals);
    setEnrich(s.enrich);
    setSelected(s.sources.filter((k) => !sources || sources.some((x) => x.key === k && x.status === "available")));
    setUsedSavedId(s.id);
    setFieldErrors({});
    setFormError(null);
    setSaveMsg({ text: `Loaded "${s.name}".`, error: false });
  }

  async function saveSearch() {
    setSaveMsg(null);
    try {
      const saved = await createSavedSearch({ ...currentInput(), name: saveName.trim() });
      setSaveName("");
      setUsedSavedId(saved.id);
      setSavedKey((n) => n + 1);
      setSaveMsg({ text: `Saved "${saved.name}".`, error: false });
    } catch (err) {
      setSaveMsg({ text: err instanceof ApiError ? err.message : "Could not save the search.", error: true });
    }
  }

  useEffect(() => {
    getSources()
      .then((list) => {
        setSources(list);
        setSelected(list.filter((s) => s.key === "npi_registry" && s.status === "available").map((s) => s.key));
      })
      .catch((e: Error) => setSourcesError(e.message));
  }, []);

  const progressKey = { specialty: specialty.trim(), state, city: city.trim(), subparts, hospitals };
  const progressId = JSON.stringify(progressKey);
  useEffect(() => {
    // how much of this search was already fetched; the next search continues after it
    if (!state || !specialty.trim()) return;
    let stale = false;
    const t = setTimeout(() => {
      getSearchProgress(JSON.parse(progressId)).then((p) => !stale && setProgress(p)).catch(() => !stale && setProgress(null));
    }, 400);
    return () => {
      stale = true;
      clearTimeout(t);
    };
  }, [progressId, state, specialty]);

  async function startOver() {
    await resetSearchProgress(progressKey);
    setProgress({ leads_fetched: 0, exhausted: false });
  }

  const currentInput = () => ({
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

  const targetNum = Number(target);
  const targetValid = Number.isInteger(targetNum) && targetNum >= 1 && targetNum <= 50000;
  const canSave = saveName.trim() !== "" && (practices || solo) && selected.length > 0 && targetValid && specialty.trim() !== "" && state !== "";
  const canSubmit =
    !submitting && (practices || solo) && selected.length > 0 && targetValid && specialty.trim() !== "" && state !== "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await createSearch(currentInput());
      if (usedSavedId) {
        touchSavedSearch(usedSavedId)
          .then(() => setSavedKey((n) => n + 1))
          .catch(() => {}); // last_run_at is a nicety, never block the search
      }
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
  const usable = visibleSources.filter((s) => s.status === "available");
  const unavailable = visibleSources.filter((s) => s.status !== "available");

  return (
    <form onSubmit={submit} className="space-y-6" noValidate>
      <SavedSearches refreshKey={savedKey} onUse={applySaved} />

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="specialty">Specialty</Label>
          <select
            id="specialty"
            value={choice}
            required
            aria-invalid={!!fieldErrors.specialty}
            aria-describedby={describe(!!fieldErrors.specialty && "specialty-error")}
            onChange={(e) => setChoice(e.target.value)}
            className={SELECT_CLASS}
          >
            {SPECIALTIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
            <option value={OTHER}>Other (type exact NPI taxonomy name)</option>
          </select>
          {choice === OTHER && (
            <>
              <Input
                aria-label="NPI taxonomy name"
                value={custom}
                maxLength={100}
                required
                aria-invalid={!!fieldErrors.specialty}
                aria-describedby={describe("specialty-hint", !!fieldErrors.specialty && "specialty-error")}
                onChange={(e) => setCustom(e.target.value)}
                className="mt-2"
              />
              <p id="specialty-hint" className="mt-1 text-sm text-muted-foreground">
                Must match an NPI taxonomy description exactly, otherwise the search finds nothing.{" "}
                <a
                  href="https://taxonomy.nucc.org/"
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-2"
                >
                  NPI taxonomy list
                </a>
              </p>
            </>
          )}
          <FieldError id="specialty-error" text={fieldErrors.specialty} />
        </div>
        <div>
          <Label htmlFor="state">State</Label>
          <select
            id="state"
            value={state}
            required
            aria-invalid={!!fieldErrors.state}
            aria-describedby={describe(!!fieldErrors.state && "state-error")}
            onChange={(e) => setState(e.target.value)}
            className={SELECT_CLASS}
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
      </div>

      <div className="grid gap-4 border-t pt-5 sm:grid-cols-2">
        <div>
          <Label htmlFor="city">City (optional)</Label>
          <Input
            id="city"
            value={city}
            maxLength={100}
            aria-invalid={!!fieldErrors.city}
            aria-describedby={describe(!!fieldErrors.city && "city-error")}
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
            max={50000}
            value={target}
            aria-invalid={!targetValid || !!fieldErrors.target_count}
            aria-describedby={describe("target-help", (!!fieldErrors.target_count || !targetValid) && "target-error")}
            onChange={(e) => setTarget(e.target.value)}
            className="mt-1"
          />
          <p id="target-help" className="mt-1 text-sm text-muted-foreground">
            Only new leads count. A repeat search continues after the leads you already fetched.
          </p>
          {state && progress && (progress.leads_fetched > 0 || progress.exhausted) && (
            <p id="progress-note" role="status" className="mt-1 text-sm">
              {progress.exhausted
                ? `All leads for this search are fetched (${progress.leads_fetched} saved). `
                : `${progress.leads_fetched} already fetched for this search; the next search continues after them. `}
              <button type="button" onClick={startOver} className="-my-1 rounded py-1 underline underline-offset-2 focus-visible:ring-3 focus-visible:ring-ring/50">
                Start over
              </button>
            </p>
          )}
          <FieldError
            id="target-error"
            text={fieldErrors.target_count ?? (targetValid ? undefined : "Enter a whole number from 1 to 50000.")}
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

      <fieldset className="space-y-2" aria-describedby={describe(!!fieldErrors.sources && "sources-error")}>
        <legend className="mb-1 text-sm font-medium">Sources</legend>
        {sources === null && !sourcesError && <p className="text-sm text-muted-foreground">Loading sources...</p>}
        {sourcesError && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            Could not load sources: {sourcesError}
          </p>
        )}
        {usable.map((s) => (
          <CheckRow
            key={s.key}
            label={s.name}
            checked={selected.includes(s.key)}
            onChange={(v) => setSelected((cur) => (v ? [...cur, s.key] : cur.filter((k) => k !== s.key)))}
          />
        ))}
        {unavailable.length > 0 && (
          <details className="rounded-lg border bg-muted/40 px-3 py-2 text-sm">
            <summary className="cursor-pointer text-muted-foreground">{unavailable.length} more sources, not usable yet</summary>
            <div className="mt-2 space-y-2">
              {unavailable.map((s) => (
                <CheckRow key={s.key} label={s.name} checked={false} disabled hint={SOURCE_STATUS_LABELS[s.status] ?? s.status} />
              ))}
            </div>
          </details>
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

      <div className="border-t pt-5">
        <Label htmlFor="save-name">Save this search</Label>
        <div className="mt-1 flex gap-2">
          <Input
            id="save-name"
            value={saveName}
            maxLength={60}
            placeholder="Name, e.g. IM Florida"
            aria-describedby={describe(!!saveMsg && "save-msg")}
            onChange={(e) => setSaveName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault(); // Enter here saves, it must not start the search
                if (canSave) saveSearch();
              }
            }}
          />
          <Button type="button" variant="outline" disabled={!canSave} onClick={saveSearch}>
            Save
          </Button>
        </div>
        {saveMsg && (
          <p id="save-msg" role="status" className={saveMsg.error ? "mt-1 text-sm text-red-700 dark:text-red-400" : "mt-1 text-sm text-muted-foreground"}>
            {saveMsg.text}
          </p>
        )}
      </div>
    </form>
  );
}
