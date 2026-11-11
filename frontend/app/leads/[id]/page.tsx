"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ActivityForm } from "@/components/activity-form";
import { ActivityTimeline } from "@/components/activity-timeline";
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
import { CRM_STATUSES, ORG_TYPES, PRIORITIES, SCORE_FACTORS } from "@/lib/constants";
import { formatPhone } from "@/lib/format";

const SELECT =
  "h-8 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

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
    <Suspense fallback={<p className="text-sm">Loading...</p>}>
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

  // Reload the lead and the first page of the timeline (status changes add entries).
  const refresh = useCallback(async () => {
    try {
      const [l, a] = await Promise.all([getLead(id), listActivities(id, 1)]);
      setLead(l);
      setActs(a.items);
      setTotal(a.total);
      setPage(1);
      setLoadError(null);
    } catch (e) {
      setLoadError(msg(e));
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
    try {
      await patchLead(id, body);
      setMessage({ text: ok, error: false });
    } catch (e) {
      setMessage({ text: `Not saved. ${msg(e)}`, error: true });
    }
    await refresh(); // on failure this restores the server value in the controls
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
  const contactName = [lead.contact?.first_name, lead.contact?.last_name].filter(Boolean).join(" ");

  return (
    <div className="space-y-6">
      <Link href="/leads" className="text-sm underline underline-offset-4">
        Back to leads
      </Link>
      <p role={message?.error ? "alert" : "status"} className={`min-h-5 text-sm ${message?.error ? "text-destructive" : ""}`}>
        {message?.text ?? ""}
      </p>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold">{lead.name}</h1>
          <Badge variant="outline">{type}</Badge>
          {priority && <Badge variant={lead.priority === "critical" || lead.priority === "high" ? "default" : "secondary"}>{priority}</Badge>}
          {lead.suppressed && <Badge variant="destructive">Suppressed</Badge>}
        </div>
        <p className="text-sm text-muted-foreground">
          {[lead.primary_taxonomy_desc, [lead.city, lead.state].filter(Boolean).join(", ")].filter(Boolean).join(" | ")}
          {" | "}Fit score {lead.fit_score ?? "-"} of 100
        </p>
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="lead-status">Sales status</Label>
            <select
              id="lead-status"
              className={SELECT}
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
              value={lead.next_follow_up_at?.slice(0, 10) ?? ""}
              onChange={(e) => save({ next_follow_up_at: e.target.value || null }, "Follow-up date saved.")}
            />
          </div>
          <Button variant="outline" disabled={lead.suppressed} onClick={suppress}>
            Add to suppression list
          </Button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <ActivityForm leadId={id} onSaved={refresh} />
          <section aria-labelledby="timeline-h" className="space-y-3">
            <h2 id="timeline-h" className="text-sm font-semibold">
              Timeline
            </h2>
            <ActivityTimeline items={acts} total={total} loading={more} onMore={loadMore} />
          </section>
        </div>

        <aside aria-label="Lead facts" className="space-y-6 text-sm">
          <section>
            <h2 className="mb-2 font-semibold">Score explanation</h2>
            {lead.score ? (
              <>
                <ul className="space-y-1">
                  {SCORE_FACTORS.map(({ key, label }) => {
                    const f = comps[key];
                    return (
                      <li key={key}>
                        <span className="font-medium">{label}:</span>{" "}
                        {f ? (
                          <>
                            {f.points} of {f.max}
                            <span className="text-muted-foreground">, {f.reason}</span>
                          </>
                        ) : (
                          <span className="text-muted-foreground">not scored</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-2">
                  <span className="font-medium">Total:</span> {lead.fit_score ?? "-"} of 100
                  <span className="text-muted-foreground"> (config {lead.score.config_version})</span>
                </p>
              </>
            ) : (
              <p className="text-muted-foreground">Not scored yet.</p>
            )}
          </section>
          <section>
            <h2 className="mb-2 font-semibold">Contacts</h2>
            <p>
              {contactName || <span className="text-muted-foreground">No named contact.</span>}
              {lead.contact?.title && <span className="text-muted-foreground">, {lead.contact.title}</span>}
            </p>
            <p className="tabular-nums">Phone {formatPhone(lead.contact?.phone ?? lead.phone)}</p>
            <p className="tabular-nums">Fax {formatPhone(lead.fax)}</p>
          </section>
          <section>
            <h2 className="mb-2 font-semibold">Locations ({lead.locations.length})</h2>
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
          <section>
            <h2 className="mb-2 font-semibold">Source</h2>
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
