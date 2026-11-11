"use client";

import { Fragment, useState } from "react";
import { LeadRowDetail } from "@/components/lead-row-detail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, patchLeadStatus, type Lead, type LeadPage } from "@/lib/api";
import { CRM_STATUSES, PRIORITIES } from "@/lib/constants";
import { formatPhone } from "@/lib/format";

const SELECT =
  "h-7 rounded-lg border border-input bg-transparent px-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

type SortCol = "score" | "name";

function SortHead({ col, label, sort, order, onSort }: { col: SortCol; label: string; sort: string; order: string; onSort: (c: SortCol) => void }) {
  const active = sort === col;
  return (
    <TableHead aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => onSort(col)} className="rounded font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        {label}
        <span aria-hidden="true">{active ? (order === "asc" ? " ▲" : " ▼") : ""}</span>
      </button>
    </TableHead>
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
  onMessage: (text: string, error: boolean) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  // Saved or in-flight status values, keyed by lead id; removed on failure so the row reverts to the server value.
  const [statusOverride, setStatusOverride] = useState<Record<string, string>>({});

  if (data.total === 0) return <p className="text-sm text-muted-foreground">No leads match these filters.</p>;

  const from = (data.page - 1) * pageSize + 1;
  const to = from + data.items.length - 1;
  const lastPage = Math.max(1, Math.ceil(data.total / pageSize));
  const allOnPage = data.items.every((l) => selected.has(l.id));
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

  async function changeStatus(lead: Lead, value: string) {
    const label = CRM_STATUSES.find((s) => s.value === value)?.label ?? value;
    setStatusOverride((o) => ({ ...o, [lead.id]: value }));
    try {
      await patchLeadStatus(lead.id, value);
      onMessage(`${lead.name}: status set to ${label}.`, false);
    } catch (e) {
      onMessage(`${lead.name}: status was not saved. ${e instanceof ApiError ? e.message : "Unknown error."}`, true);
      setStatusOverride((o) => {
        const next = { ...o };
        delete next[lead.id]; // revert to the server value
        return next;
      });
    }
  }

  return (
    <div className="space-y-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <Checkbox
                aria-label="Select all leads on this page"
                checked={allOnPage}
                indeterminate={someOnPage && !allOnPage}
                onCheckedChange={(v) => togglePage(v)}
              />
            </TableHead>
            <SortHead col="name" label="Organization" sort={sort} order={order} onSort={onSort} />
            <TableHead>Specialty</TableHead>
            <TableHead>City, state</TableHead>
            <TableHead>Phone</TableHead>
            <TableHead>Primary contact</TableHead>
            <SortHead col="score" label="Score" sort={sort} order={order} onSort={onSort} />
            <TableHead>Priority</TableHead>
            <TableHead>Sales status</TableHead>
            <TableHead>Updated</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((l) => {
            const open = expanded === l.id;
            const detailId = `detail-${l.id}`;
            const contactName = [l.contact?.first_name, l.contact?.last_name].filter(Boolean).join(" ");
            const priority = PRIORITIES.find((p) => p.value === l.priority)?.label;
            return (
              <Fragment key={l.id}>
                <TableRow
                  className="cursor-pointer"
                  data-state={selected.has(l.id) ? "selected" : undefined}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("button,select,input,[role=checkbox],label")) return;
                    setExpanded(open ? null : l.id);
                  }}
                >
                  <TableCell>
                    <Checkbox aria-label={`Select ${l.name}`} checked={selected.has(l.id)} onCheckedChange={(v) => toggle(l.id, v)} />
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    <button
                      type="button"
                      aria-expanded={open}
                      aria-controls={detailId}
                      onClick={() => setExpanded(open ? null : l.id)}
                      className="rounded text-left font-medium outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <span aria-hidden="true">{open ? "▾ " : "▸ "}</span>
                      {l.name}
                      <span className="sr-only">{open ? ", hide details" : ", show details"}</span>
                    </button>
                    {l.organization_type === "solo_provider" && (
                      <Badge variant="outline" className="ml-2">
                        Solo
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-normal">{l.primary_taxonomy_desc ?? "-"}</TableCell>
                  <TableCell>{[l.city, l.state].filter(Boolean).join(", ") || "-"}</TableCell>
                  <TableCell className="tabular-nums">{formatPhone(l.phone)}</TableCell>
                  <TableCell className="whitespace-normal">
                    {contactName ? (
                      <>
                        {contactName}
                        {l.contact?.title && <span className="text-muted-foreground">, {l.contact.title}</span>}
                      </>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell className="tabular-nums">{l.fit_score ?? "-"}</TableCell>
                  <TableCell>{priority ? <Badge variant={l.priority === "critical" || l.priority === "high" ? "default" : "secondary"}>{priority}</Badge> : "-"}</TableCell>
                  <TableCell>
                    <select
                      aria-label={`Sales status for ${l.name}`}
                      className={SELECT}
                      value={statusOverride[l.id] ?? l.crm_status}
                      onChange={(e) => changeStatus(l, e.target.value)}
                    >
                      {CRM_STATUSES.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </TableCell>
                  <TableCell className="whitespace-nowrap">{new Date(l.updated_at).toLocaleDateString()}</TableCell>
                </TableRow>
                {open && (
                  <TableRow id={detailId} className="bg-muted/30 hover:bg-muted/30">
                    <TableCell colSpan={10} className="whitespace-normal p-0">
                      <LeadRowDetail lead={l} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
      <nav aria-label="Pagination" className="flex items-center justify-between gap-3 text-sm">
        <p>
          {from} to {to} of {data.total}
        </p>
        <div className="flex gap-2">
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
