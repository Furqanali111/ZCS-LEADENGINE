"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight, Columns3, Globe, Mail } from "lucide-react";
import Link from "next/link";
import { Fragment, useEffect, useRef, useState } from "react";
import { LeadRowDetail } from "@/components/lead-row-detail";
import { priorityTone, statusTone, ToneBadge } from "@/components/tone-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, patchLead, patchLeadStatus, type Lead, type LeadPage } from "@/lib/api";
import { CLOSED_STATUSES, CRM_STATUSES, PRIORITIES } from "@/lib/constants";
import { SELECT_CLASS } from "@/lib/ui";
import { isOverdue } from "@/lib/dates";
import { OPTIONAL_COLUMNS, setColumnHidden, useHiddenColumns } from "@/lib/columns";
import { formatDay, formatPhone, hostOf, safeHttpUrl } from "@/lib/format";

// The select itself is the colored status pill; same tone tokens as ToneBadge.
const PILL =
  "h-8 w-44 cursor-pointer rounded-full border border-transparent px-2.5 text-xs font-medium outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";
const PILL_TONE = {
  danger: "bg-tone-danger-bg text-tone-danger-fg",
  warning: "bg-tone-warning-bg text-tone-warning-fg",
  success: "bg-tone-success-bg text-tone-success-fg",
  info: "bg-tone-info-bg text-tone-info-fg",
  neutral: "bg-tone-neutral-bg text-tone-neutral-fg",
} as const;
const LINK = "rounded-sm underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50";
const NONE = (
  <span className="text-muted-foreground">
    <span aria-hidden>-</span>
    <span className="sr-only">None</span>
  </span>
);

const closed = new Set(CLOSED_STATUSES.map((s) => s.value));

export const PAGE_SIZES = [25, 50, 100, 200];

type SortCol = "score" | "name" | "follow_up" | "email" | "website";

function SortHead({ col, label, sort, order, onSort }: { col: SortCol; label: string; sort: string; order: string; onSort: (c: SortCol) => void }) {
  const active = sort === col;
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() => onSort(col)}
        className={`-mx-1 inline-flex items-center gap-1 rounded px-1 py-0.5 font-semibold hover:text-foreground ${active ? "text-foreground" : ""}`}
      >
        {label}
        <Icon aria-hidden className={`size-3 ${active ? "" : "opacity-50"}`} />
      </button>
    </TableHead>
  );
}

function Score({ value }: { value: number | null }) {
  if (value === null) return NONE;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="font-semibold tabular-nums">{value}</span>
    </span>
  );
}

export function LeadsTable({
  data,
  sort,
  order,
  pageSize,
  selected,
  onSelect,
  onSort,
  onPage,
  onPageSize,
  onMessage,
}: {
  data: LeadPage;
  sort: string;
  order: string;
  pageSize: number;
  selected: Set<string>;
  onSelect: (s: Set<string>) => void;
  onSort: (c: SortCol) => void;
  onPage: (p: number) => void;
  onPageSize: (n: number) => void;
  onMessage: (text: string, error: boolean) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const colsMenu = useRef<HTMLDetailsElement>(null);
  // Native <details> has no dismiss: close on an outside click (Escape and focus-out are handled on the element).
  useEffect(() => {
    const away = (e: MouseEvent) => {
      const d = colsMenu.current;
      if (d?.open && !d.contains(e.target as Node)) d.open = false;
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, []);
  const hidden = useHiddenColumns();
  const show = (k: string) => !hidden.has(k);
  const colCount = 4 + OPTIONAL_COLUMNS.filter((c) => show(c.key)).length; // checkbox, organization, score, status
  // Saved or in-flight status values, keyed by lead id; removed on failure so the row reverts to the server value.
  const [sentOverride, setSentOverride] = useState<Record<string, boolean>>({});
  const [statusOverride, setStatusOverride] = useState<Record<string, string>>({});
  // One request per row at a time, so the shown value never has two writers.
  const [pending, setPending] = useState<Set<string>>(new Set());

  if (data.total === 0) {
    return <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">No leads match these filters.</p>;
  }

  if (data.items.length === 0) {
    return (
      <p className="rounded-xl border border-dashed bg-card p-8 text-center text-sm text-muted-foreground">
        This page is past the end of the list.{" "}
        <Button variant="outline" size="sm" onClick={() => onPage(Math.max(1, Math.ceil(data.total / pageSize)))}>
          Go to the last page
        </Button>
      </p>
    );
  }

  const from = (data.page - 1) * pageSize + 1;
  const to = from + data.items.length - 1;
  const lastPage = Math.max(1, Math.ceil(data.total / pageSize));
  const allOnPage = data.items.length > 0 && data.items.every((l) => selected.has(l.id));
  const someOnPage = data.items.some((l) => selected.has(l.id));

  function toggle(id: string, on: boolean) {
    const next = new Set(selected);
    if (on) next.add(id);
    else next.delete(id);
    onSelect(next);
  }
  function togglePage(on: boolean) {
    const next = new Set(selected);
    for (const l of data.items) {
      if (on) next.add(l.id);
      else next.delete(l.id);
    }
    onSelect(next);
  }

  async function changeSent(lead: Lead, value: boolean) {
    setPending((p) => new Set(p).add(lead.id));
    setSentOverride((o) => ({ ...o, [lead.id]: value }));
    try {
      await patchLead(lead.id, { email_sent: value });
      onMessage(`${lead.name}: email marked as ${value ? "sent" : "not sent"}.`, false);
    } catch (e) {
      onMessage(`${lead.name}: email status was not saved. ${e instanceof ApiError ? e.message : "Unknown error."}`, true);
      setSentOverride((o) => {
        const next = { ...o };
        delete next[lead.id];
        return next;
      });
    } finally {
      setPending((p) => {
        const n = new Set(p);
        n.delete(lead.id);
        return n;
      });
    }
  }

  async function changeStatus(lead: Lead, value: string) {
    const label = CRM_STATUSES.find((s) => s.value === value)?.label ?? value;
    const previous = statusOverride[lead.id]; // last value shown, restored on failure
    setPending((p) => new Set(p).add(lead.id));
    setStatusOverride((o) => ({ ...o, [lead.id]: value }));
    try {
      await patchLeadStatus(lead.id, value);
      onMessage(`${lead.name}: status set to ${label}.`, false);
    } catch (e) {
      onMessage(`${lead.name}: status was not saved. ${e instanceof ApiError ? e.message : "Unknown error."}`, true);
      setStatusOverride((o) => {
        const next = { ...o };
        if (previous === undefined) delete next[lead.id]; // fall back to the server value
        else next[lead.id] = previous;
        return next;
      });
    } finally {
      setPending((p) => {
        const n = new Set(p);
        n.delete(lead.id);
        return n;
      });
    }
  }

  return (
    <div className="space-y-3">
      <details
        ref={colsMenu}
        className="relative ml-auto w-fit text-sm"
        onKeyDown={(e) => {
          if (e.key !== "Escape" || !e.currentTarget.open) return;
          e.currentTarget.open = false;
          e.currentTarget.querySelector("summary")?.focus();
        }}
        onBlur={(e) => {
          if (e.currentTarget.open && !e.currentTarget.contains(e.relatedTarget as Node | null)) e.currentTarget.open = false;
        }}
      >
        <summary className="inline-flex h-9 cursor-pointer list-none items-center gap-1.5 rounded-lg border bg-background px-3 font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
          <Columns3 aria-hidden className="size-4" />
          Columns
        </summary>
        <fieldset className="absolute right-0 z-20 mt-1 w-48 rounded-lg border bg-popover p-2 text-popover-foreground shadow-md">
          <legend className="sr-only">Visible columns</legend>
          {OPTIONAL_COLUMNS.map((c) => (
            <label key={c.key} className="flex min-h-8 cursor-pointer items-center gap-2 rounded px-1.5 hover:bg-muted">
              <input type="checkbox" className="size-4" checked={show(c.key)} onChange={(e) => setColumnHidden(c.key, !e.target.checked, hidden)} />
              {c.label}
            </label>
          ))}
        </fieldset>
      </details>
      <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <Table containerClassName="max-h-[calc(100vh-18rem)] min-h-64" className="min-w-[72rem] text-[13px]">
          <TableHeader className="[&_th]:sticky [&_th]:top-0 [&_th]:z-10 [&_th]:bg-muted [&_th]:shadow-[inset_0_-1px_0_var(--border)]">
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8">
                <Checkbox
                  aria-label="Select all leads on this page"
                  checked={allOnPage}
                  indeterminate={someOnPage && !allOnPage}
                  onCheckedChange={(v) => togglePage(v)}
                />
              </TableHead>
              <SortHead col="name" label="Organization" sort={sort} order={order} onSort={onSort} />
              {show("specialty") && <TableHead className="min-w-36">Specialty</TableHead>}
              {show("location") && <TableHead>City, state</TableHead>}
              {show("phone") && <TableHead>Phone</TableHead>}
              {show("contact") && <TableHead className="min-w-44">Primary contact</TableHead>}
              {show("website") && <SortHead col="website" label="Website" sort={sort} order={order} onSort={onSort} />}
              {show("email") && <SortHead col="email" label="Email" sort={sort} order={order} onSort={onSort} />}
              <SortHead col="score" label="Score" sort={sort} order={order} onSort={onSort} />
              {show("priority") && <TableHead>Priority</TableHead>}
              <TableHead>Sales status</TableHead>
              {show("email_sent") && <TableHead>Email sent</TableHead>}
              {show("email_owner") && <TableHead>Email sent by</TableHead>}
              {show("owner") && <TableHead>Owner</TableHead>}
              {show("follow_up") && <SortHead col="follow_up" label="Follow-up" sort={sort} order={order} onSort={onSort} />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((l) => {
              const open = expanded === l.id;
              const detailId = `detail-${l.id}`;
              const contactName = [l.contact?.first_name, l.contact?.last_name].filter(Boolean).join(" ");
              const priority = PRIORITIES.find((p) => p.value === l.priority)?.label;
              const site = safeHttpUrl(l.website);
              const status = statusOverride[l.id] ?? l.crm_status;
              const contactText = contactName ? `${contactName}${l.contact?.title ? `, ${l.contact.title}` : ""}` : "";
              return (
                <Fragment key={l.id}>
                  <TableRow
                    className="cursor-pointer"
                    data-state={selected.has(l.id) ? "selected" : undefined}
                    onClick={(e) => {
                      if ((e.target as HTMLElement).closest("a,button,select,input,[role=checkbox],label")) return;
                      setExpanded(open ? null : l.id);
                    }}
                  >
                    <TableCell>
                      <Checkbox aria-label={`Select ${l.name}`} checked={selected.has(l.id)} onCheckedChange={(v) => toggle(l.id, v)} />
                    </TableCell>
                    <TableCell className="min-w-44 whitespace-normal">
                      <div className="flex items-start gap-1">
                        <button
                          type="button"
                          aria-expanded={open}
                          aria-controls={detailId}
                          aria-label={`${open ? "Hide" : "Show"} details for ${l.name}`}
                          onClick={() => setExpanded(open ? null : l.id)}
                          className="-ml-1 shrink-0 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
                        >
                          {open ? <ChevronDown aria-hidden className="size-4" /> : <ChevronRight aria-hidden className="size-4" />}
                        </button>
                        <Link href={`/lead?id=${l.id}`} className={`font-medium ${LINK}`}>
                          {l.name}
                        </Link>
                        {l.organization_type === "solo_provider" && (
                          <Badge variant="outline" className="ml-1 shrink-0">
                            Solo
                          </Badge>
                        )}
                        {l.suppressed && <ToneBadge tone="danger" className="ml-1 shrink-0">Suppressed</ToneBadge>}
                      </div>
                    </TableCell>
                    {show("specialty") && (
                      <TableCell className="min-w-36 whitespace-normal" title={l.primary_taxonomy_desc ?? undefined}>
                        {l.primary_taxonomy_desc ?? NONE}
                      </TableCell>
                    )}
                    {show("location") && (
                      <TableCell className="w-28 whitespace-normal">{[l.city, l.state].filter(Boolean).join(", ") || NONE}</TableCell>
                    )}
                    {show("phone") && (
                      <TableCell className="whitespace-nowrap font-semibold tabular-nums text-foreground">{l.phone ? formatPhone(l.phone) : NONE}</TableCell>
                    )}
                    {show("contact") && (
                      <TableCell className="min-w-44 whitespace-normal" title={contactText || undefined}>
                        {contactName ? (
                          <>
                            {contactName}
                            {l.contact?.title && <span className="text-muted-foreground">, {l.contact.title}</span>}
                          </>
                        ) : (
                          NONE
                        )}
                      </TableCell>
                    )}
                    {show("website") && (
                      <TableCell className="max-w-28">
                        {site ? (
                          <a href={site} target="_blank" rel="noopener noreferrer" title={l.website ?? undefined} className={`flex items-center gap-1.5 ${LINK}`}>
                            <Globe aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
                            <span className="truncate">{hostOf(l.website!)}</span>
                            <span className="sr-only"> (opens in a new tab)</span>
                          </a>
                        ) : (
                          NONE
                        )}
                      </TableCell>
                    )}
                    {show("email") && (
                      <TableCell className="max-w-36">
                        {l.primary_email ? (
                          <span className="flex items-center gap-1.5" title={l.primary_email}>
                            <Mail aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
                            <span className="truncate">{l.primary_email}</span>
                          </span>
                        ) : (
                          NONE
                        )}
                      </TableCell>
                    )}
                    <TableCell>
                      <Score value={l.fit_score} />
                    </TableCell>
                    {show("priority") && (
                      <TableCell>{priority ? <ToneBadge tone={priorityTone(l.priority)}>{priority}</ToneBadge> : NONE}</TableCell>
                    )}
                    <TableCell>
                      <select
                        aria-label={`Sales status for ${l.name}`}
                        className={`${PILL} ${PILL_TONE[statusTone(status)]}`}
                        value={status}
                        disabled={pending.has(l.id)}
                        onChange={(e) => changeStatus(l, e.target.value)}
                      >
                        {CRM_STATUSES.map((s) => (
                          <option key={s.value} value={s.value} title={s.hint} className="bg-popover text-popover-foreground">
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </TableCell>
                    {show("email_sent") && (
                      <TableCell>
                        <label className="inline-flex cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            className="size-4"
                            aria-label={`Email sent to ${l.name}`}
                            checked={sentOverride[l.id] ?? l.email_sent}
                            disabled={pending.has(l.id)}
                            onChange={(e) => changeSent(l, e.target.checked)}
                          />
                          {(sentOverride[l.id] ?? l.email_sent) ? "Sent" : <span className="text-muted-foreground">Not sent</span>}
                        </label>
                      </TableCell>
                    )}
                    {show("email_owner") && (
                      <TableCell>{l.email_sent && l.email_sent_by ? <ToneBadge tone="info">{l.email_sent_by}</ToneBadge> : NONE}</TableCell>
                    )}
                    {show("owner") && (
                      <TableCell>{l.owner ? <ToneBadge tone="warning">{l.owner}</ToneBadge> : NONE}</TableCell>
                    )}
                    {show("follow_up") && (
                      <TableCell>
                        {l.next_follow_up_at ? (
                          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
                            {formatDay(l.next_follow_up_at)}
                            {isOverdue(l.next_follow_up_at) && !closed.has(status) && <ToneBadge tone="danger">Overdue</ToneBadge>}
                          </span>
                        ) : (
                          NONE
                        )}
                      </TableCell>
                    )}
                    </TableRow>
                  {open && (
                    <TableRow id={detailId} className="bg-muted/40 hover:bg-muted/40">
                      <TableCell colSpan={colCount} className="whitespace-normal p-0">
                        <LeadRowDetail lead={l} />
                        <p className="px-4 pb-3 text-xs text-muted-foreground">Updated {new Date(l.updated_at).toLocaleDateString()}</p>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <nav aria-label="Pagination" className="flex items-center justify-between gap-3 text-sm">
        <p className="text-muted-foreground">
          {from} to {to} of {data.total}
        </p>
        <div className="flex items-center gap-2">
          <label htmlFor="page-size" className="text-muted-foreground">
            Per page
          </label>
          <select id="page-size" className={`${SELECT_CLASS} !h-9 !w-auto`} value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}>
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>
            Previous
          </Button>
          <Button variant="outline" size="sm" disabled={data.page >= lastPage} onClick={() => onPage(data.page + 1)}>
            Next
          </Button>
        </div>
      </nav>
    </div>
  );
}
