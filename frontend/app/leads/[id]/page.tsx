"use client";

import { ArrowLeft, Globe, ShieldBan } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ActivityForm } from "@/components/activity-form";
import { ActivityTimeline } from "@/components/activity-timeline";
import { priorityTone, statusTone, ToneBadge } from "@/components/tone-badge";
import { LeadTemplates } from "@/components/lead-templates";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  addSuppression,
  ApiError,
  getLead,
  listActivities,
  patchLead,
  type Activity,
  type Lead,
  type LeadPatch,
} from "@/lib/api";
import { PANEL_CLASS, SELECT_CLASS } from "@/lib/ui";
import { CRM_STATUSES, ORG_TYPES, PRIORITIES, SCORE_FACTORS } from "@/lib/constants";
import { formatPhone, hostOf, pagePath, safeHttpUrl } from "@/lib/format";
import { ContactStrip } from "@/components/contact-strip";

type Factor = { points: number; max: number; reason: string };

const msg = (e: unknown) => (e instanceof ApiError ? e.message : "Unknown error.");

function address(l: Lead["locations"][number]) {
  const street = [l.address_1, l.address_2].filter(Boolean).join(", ");
  const place = [l.city, [l.state, l.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  return [street, place].filter(Boolean).join(", ") || "No address";
}

// Suspense is required: reading route params at request time is dynamic under cacheComponents.
export default function LeadDetailPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading...</p>}>
      <LeadDetail />
    </Suspense>
  );
}

function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<Lead | null>(null);
  const [acts, setActs] = useState<Activity[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [followDraft, setFollowDraft] = useState<string | null>(null);
  const refreshSeq = useRef(0);
  const webHeading = useRef<HTMLHeadingElement>(null);

  // Reload the lead and the first page of the timeline (status changes add entries).
  const refresh = useCallback(async () => {
    const seq = ++refreshSeq.current;
    try {
      const [l, a] = await Promise.all([getLead(id), listActivities(id, 1)]);
      if (seq !== refreshSeq.current) return; // a newer refresh is in flight; drop this stale result
      setLead(l);
      setActs(a.items);
      setTotal(a.total);
      setPage(1);
      setLoadError(null);
    } catch (e) {
      if (seq === refreshSeq.current) setLoadError(msg(e));
    }
  }, [id]);

  useEffect(() => {
    // Initial fetch; refresh() sets state only after the awaited requests resolve.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  async function loadMore() {
    setMore(true);
    try {
      const a = await listActivities(id, page + 1);
      setActs((cur) => [...cur, ...a.items.filter((n) => !cur.some((c) => c.id === n.id))]);
      setTotal(a.total);
      setPage(page + 1);
    } catch (e) {
      setMessage({ text: `Could not load more. ${msg(e)}`, error: true });
    } finally {
      setMore(false);
    }
  }

  async function save(body: LeadPatch, ok: string) {
    let saved = false;
    try {
      await patchLead(id, body);
      setMessage({ text: ok, error: false });
      saved = true;
    } catch (e) {
      setMessage({ text: `Not saved. ${msg(e)}`, error: true });
    }
    await refresh(); // on failure this restores the server value in the controls
    return saved;
  }

  // Saves a typed date only when it is empty or complete; otherwise waits for blur.
  function saveFollow(value: string) {
    setFollowDraft(null);
    if (value === (lead?.next_follow_up_at?.slice(0, 10) ?? "")) return;
    void save({ next_follow_up_at: value || null }, "Follow-up date saved.");
  }

  async function rejectWebsite() {
    if (!lead?.website) return;
    if (!window.confirm(`Remove ${hostOf(lead.website)} as the website for ${lead.name}? Its emails and people found there will be removed too.`)) return;
    if (await save({ reject_website: true }, "Website removed.")) webHeading.current?.focus();
    // on success the button is gone, so focus moves to the section heading
  }

  async function suppress() {
    if (!lead) return;
    if (!window.confirm(`Add NPI ${lead.npi} to the suppression list? ${lead.name} will be marked do not contact.`)) return;
    try {
      await addSuppression({ kind: "npi", value: lead.npi, reason: "Added from lead detail" });
      setMessage({ text: "Added to the suppression list.", error: false });
    } catch (e) {
      setMessage({ text: `Not suppressed. ${msg(e)}`, error: true });
    }
    await refresh();
  }

  if (!lead) {
    return (
      <div className="space-y-3">
        <Link href="/leads" className="text-sm underline underline-offset-4">
          Back to leads
        </Link>
        <p role={loadError ? "alert" : "status"} className="text-sm">
          {loadError ? `Could not load this lead. ${loadError}` : "Loading..."}
        </p>
      </div>
    );
  }

  const comps = (lead.score?.components ?? {}) as Record<string, Factor>;
  const priority = PRIORITIES.find((p) => p.value === lead.priority)?.label;
  const type = ORG_TYPES.find((o) => o.value === lead.organization_type)?.label ?? lead.organization_type;
  const site = safeHttpUrl(lead.website);
  const ev = lead.website_evidence;
  const evidence = ev?.check
    ? `${ev.check === "phone" ? "Phone" : "Name and city"} matched${ev.page_url ? ` on ${pagePath(ev.page_url)}` : ""}`
    : null;
  const found = lead.contacts.filter((c) => c.email || c.source_url);
  const contactName = [lead.contact?.first_name, lead.contact?.last_name].filter(Boolean).join(" ");
  const primaryEmail = lead.contacts.map((c) => c.email ?? (c.role === "general" ? c.last_name : null)).find(Boolean) ?? null;

  return (
    <div className="space-y-5">
      <Link href="/leads" className="inline-flex items-center gap-1.5 rounded-sm text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft aria-hidden className="size-4" />
        Back to leads
      </Link>
      <div className="text-sm">
        <p role="status" className="text-muted-foreground">{message && !message.error ? message.text : ""}</p>
        <p role="alert" className="text-destructive">
          {message?.error ? message.text : ""}
        </p>
      </div>

      <header className={`${PANEL_CLASS} flex flex-wrap items-start justify-between gap-x-8 gap-y-4 p-5`}>
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{lead.name}</h1>
            <Badge variant="outline">{type}</Badge>
            {priority && <ToneBadge tone={priorityTone(lead.priority)}>{priority} priority</ToneBadge>}
            <ToneBadge tone={statusTone(lead.crm_status)}>{CRM_STATUSES.find((s) => s.value === lead.crm_status)?.label ?? lead.crm_status}</ToneBadge>
            {lead.suppressed && <ToneBadge tone="danger">Suppressed</ToneBadge>}
          </div>
          <p className="text-sm text-muted-foreground">
            {[lead.primary_taxonomy_desc, [lead.city, lead.state].filter(Boolean).join(", ")].filter(Boolean).join(" | ")}
          </p>
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="lead-status">Sales status</Label>
              <select
                id="lead-status"
                className={SELECT_CLASS}
                value={lead.crm_status}
                onChange={(e) => save({ crm_status: e.target.value }, "Status saved.")}
              >
                {CRM_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lead-follow">Next follow-up</Label>
              <Input
                id="lead-follow"
                type="date"
                className="w-auto"
                value={followDraft ?? lead.next_follow_up_at?.slice(0, 10) ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "" || /^[12]\d{3}-\d{2}-\d{2}$/.test(v)) saveFollow(v);
                  else setFollowDraft(v);
                }}
                onBlur={(e) => {
                  const v = e.target.value;
                  if (followDraft !== null && (v === "" || /^[12]\d{3}-\d{2}-\d{2}$/.test(v))) saveFollow(v);
                  else setFollowDraft(null);
                }}
              />
            </div>
            <Button variant="outline" disabled={lead.suppressed} onClick={suppress}>
              <ShieldBan aria-hidden />
              Add to suppression list
            </Button>
          </div>
        </div>
        <div className="min-w-44 space-y-1.5 text-right">
          <p className="text-sm text-muted-foreground">Fit score</p>
          <p className="text-4xl font-semibold tracking-tight tabular-nums">
            {lead.fit_score ?? "-"}
            <span className="text-base font-normal text-muted-foreground"> of 100</span>
          </p>
          <span aria-hidden className="block h-2 overflow-hidden rounded-full bg-muted">
            <span className="block h-full rounded-full bg-chart-1" style={{ width: `${Math.min(100, Math.max(0, lead.fit_score ?? 0))}%` }} />
          </span>
        </div>
      </header>

      <ContactStrip
        person={contactName}
        title={lead.contact?.title ?? null}
        phone={lead.contact?.phone ?? lead.phone}
        fax={lead.fax}
        email={primaryEmail}
        website={lead.website}
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-5">
          <ActivityForm leadId={id} onSaved={refresh} />
          <section aria-labelledby="timeline-h" className={`${PANEL_CLASS} space-y-3`}>
            <h2 id="timeline-h" className="text-sm font-semibold">
              Timeline
            </h2>
            <ActivityTimeline items={acts} total={total} loading={more} onMore={loadMore} />
          </section>
        </div>

        <aside aria-label="Lead facts" className="grid content-start gap-5 text-sm md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2 [&_h2]:text-sm [&_h2]:font-semibold [&>section]:min-w-0">
          <section className={`${PANEL_CLASS} md:col-span-2 xl:col-span-1 2xl:col-span-2`}>
            <h2 className="mb-2">Score explanation</h2>
            {lead.score ? (
              <>
                <ul className="space-y-1.5">
                  {SCORE_FACTORS.map(({ key, label }) => {
                    const f = comps[key];
                    return (
                      <li key={key}>
                        <span className="font-medium">{label}:</span>{" "}
                        {f ? (
                          <>
                            {f.points} of {f.max}
                            <span className="text-muted-foreground">, {f.reason}</span>
                            <span aria-hidden className="mt-1 block h-1 overflow-hidden rounded-full bg-muted">
                              <span className="block h-full rounded-full bg-chart-1" style={{ width: `${f.max ? Math.min(100, (f.points / f.max) * 100) : 0}%` }} />
                            </span>
                          </>
                        ) : (
                          <span className="text-muted-foreground">not scored</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-3 border-t pt-2">
                  <span className="font-medium">Total:</span> {lead.fit_score ?? "-"} of 100
                  <span className="text-muted-foreground"> (config {lead.score.config_version})</span>
                </p>
              </>
            ) : (
              <p className="text-muted-foreground">Not scored yet.</p>
            )}
          </section>
          <LeadTemplates lead={lead} />
          <section aria-labelledby="web-h" className={PANEL_CLASS}>
            <h2 id="web-h" ref={webHeading} tabIndex={-1} className="mb-2 outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
              Website and emails
            </h2>
            {lead.website ? (
              <>
                <p className="break-all">
                  {site ? (
                    <a href={site} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-primary underline underline-offset-4">
                      <Globe aria-hidden className="size-4 shrink-0" />
                      {hostOf(lead.website)}
                      <span className="sr-only"> (opens in a new tab)</span>
                    </a>
                  ) : (
                    lead.website
                  )}
                </p>
                {evidence && <p className="text-muted-foreground">{evidence}</p>}
                <Button variant="outline" size="sm" className="mt-2" aria-label={`Not this website: ${hostOf(lead.website)}`} onClick={rejectWebsite}>
                  Not this website
                </Button>
              </>
            ) : (
              <p className="text-muted-foreground">
                {lead.enrichment_status === "no_website_found" ? "No matching website found." : "No website on record."}
              </p>
            )}
            {found.length > 0 && (
              <ul className="mt-3 space-y-2 border-t pt-3">
                {found.map((c, i) => {
                  const src = safeHttpUrl(c.source_url);
                  const who = c.role === "general" ? "General address" : [c.first_name, c.last_name].filter(Boolean).join(" ");
                  const address = c.email ?? (c.role === "general" ? c.last_name : null);
                  return (
                    <li key={i}>
                      {who && <span className="font-medium">{who}</span>}
                      {c.title && <span className="text-muted-foreground">{who ? ", " : ""}{c.title}</span>}
                      {address && <p className="break-all">{address}</p>}
                      <p className="text-muted-foreground">
                        {c.email && <>Found on page{" | "}</>}
                        {src ? (
                          <a href={src} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4">
                            Source<span className="sr-only"> (opens in a new tab)</span>
                          </a>
                        ) : (
                          "No source link"
                        )}
                        {c.collected_at && <> | Collected {new Date(c.collected_at).toLocaleDateString()}</>}
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
          <section className={PANEL_CLASS}>
            <h2 className="mb-2">Locations ({lead.locations.length})</h2>
            {lead.locations.length === 0 ? (
              <p className="text-muted-foreground">No locations on record.</p>
            ) : (
              <ul className="space-y-2">
                {lead.locations.map((l, i) => (
                  <li key={i}>
                    <span className="font-medium">{l.purpose ?? "Location"}</span>
                    {l.is_primary && <span className="text-muted-foreground"> (primary)</span>}
                    <br />
                    {address(l)}
                    {l.phone && <span className="text-muted-foreground">, {formatPhone(l.phone)}</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className={PANEL_CLASS}>
            <h2 className="mb-2">Source</h2>
            {lead.source ? (
              <p>
                {lead.source.source_key}
                <br />
                <span className="text-muted-foreground">Collected {new Date(lead.source.collected_at).toLocaleString()}</span>
              </p>
            ) : (
              <p className="text-muted-foreground">No source recorded.</p>
            )}
            <p className="text-muted-foreground">NPI {lead.npi}</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
