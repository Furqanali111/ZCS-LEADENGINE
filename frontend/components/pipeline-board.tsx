"use client";

import { useCallback, useEffect, useState } from "react";
import { PipelineCard } from "@/components/pipeline-card";
import { Button } from "@/components/ui/button";
import { ApiError, getPipeline, getPipelineColumn, patchLead, type PipelineCard as Card, type PipelineColumn } from "@/lib/api";
import { CRM_STATUSES } from "@/lib/constants";

const LABELS = Object.fromEntries(CRM_STATUSES.map((s) => [s.value, s.label]));
const msg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed");

export function PipelineBoard() {
  const [cols, setCols] = useState<PipelineColumn[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [over, setOver] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState<string | null>(null);

  useEffect(() => {
    getPipeline().then((r) => setCols(r.columns), (e) => setError(msg(e)));
  }, []);

  const move = useCallback(async (card: Card, from: string, to: string) => {
    if (from === to) return;
    setError(null);
    let index = 0;
    setBusy((b) => new Set(b).add(card.id));
    setCols((cs) =>
      cs && cs.map((c) => {
        if (c.status === from) {
          index = Math.max(0, c.leads.findIndex((l) => l.id === card.id));
          return { ...c, count: c.count - 1, leads: c.leads.filter((l) => l.id !== card.id) };
        }
        if (c.status === to) return { ...c, count: c.count + 1, leads: [card, ...c.leads] };
        return c;
      }),
    );
    try {
      await patchLead(card.id, { crm_status: to });
      // Counts only (limit 1): keeps the cards already loaded in each column.
      const [a, b] = await Promise.all([getPipelineColumn(from, 0, 1), getPipelineColumn(to, 0, 1)]);
      setCols((cs) => cs && cs.map((c) => (c.status === from ? { ...c, count: a.count } : c.status === to ? { ...c, count: b.count } : c)));
    } catch (e) {
      // Restore only the two affected columns so other in-flight moves survive.
      setCols((cs) =>
        cs && cs.map((c) => {
          if (c.status === to) return { ...c, count: c.count - 1, leads: c.leads.filter((l) => l.id !== card.id) };
          if (c.status === from) {
            const leads = c.leads.filter((l) => l.id !== card.id);
            leads.splice(index, 0, card);
            return { ...c, count: c.count + 1, leads };
          }
          return c;
        }),
      );
      setError(`Could not move ${card.name} to ${LABELS[to]}: ${msg(e)}`);
    } finally {
      setBusy((b) => {
        const n = new Set(b);
        n.delete(card.id);
        return n;
      });
    }
  }, []);

  async function loadMore(col: PipelineColumn) {
    setLoadingMore(col.status);
    try {
      const r = await getPipelineColumn(col.status, col.leads.length);
      setCols((cs) =>
        cs && cs.map((c) => {
          if (c.status !== col.status) return c;
          const seen = new Set(c.leads.map((l) => l.id));
          return { ...c, count: r.count, leads: [...c.leads, ...r.leads.filter((l) => !seen.has(l.id))] };
        }),
      );
    } catch (e) {
      setError(msg(e));
    } finally {
      setLoadingMore(null);
    }
  }

  function onDrop(e: React.DragEvent, to: string) {
    e.preventDefault();
    setOver(null);
    try {
      const { id, from } = JSON.parse(e.dataTransfer.getData("text/plain"));
      const card = cols?.find((c) => c.status === from)?.leads.find((l) => l.id === id);
      if (card && to !== from) void move(card, from, to);
    } catch {
      // Not one of our cards (e.g. dragged text): ignore.
    }
  }

  if (!cols) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">{error}</p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading pipeline...</p>
    );
  }

  return (
    <div>
      {error && (
        <p role="alert" className="mb-3 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}
      <div className="flex gap-3 overflow-x-auto pb-3">
        {cols.map((col) => (
          <section
            key={col.status}
            aria-labelledby={`col-${col.status}`}
            onDragOver={(e) => {
              e.preventDefault();
              setOver(col.status);
            }}
            onDragLeave={() => setOver((o) => (o === col.status ? null : o))}
            onDrop={(e) => onDrop(e, col.status)}
            className={`w-64 shrink-0 rounded-lg border bg-muted/40 p-2 ${over === col.status ? "ring-2 ring-ring" : ""}`}
          >
            <h2 id={`col-${col.status}`} className="mb-2 flex items-center justify-between px-1 text-sm font-semibold">
              {LABELS[col.status] ?? col.status}
              <span className="font-normal text-muted-foreground" aria-label={`${col.count} leads`}>{col.count}</span>
            </h2>
            <ul className="flex min-h-12 flex-col gap-2">
              {col.leads.map((card) => (
                <PipelineCard key={card.id} card={card} status={col.status} busy={busy.has(card.id)} onMove={(c, to) => void move(c, col.status, to)} />
              ))}
            </ul>
            {col.leads.length === 0 && <p className="px-1 py-2 text-xs text-muted-foreground">No leads</p>}
            {col.leads.length < col.count && (
              <Button variant="outline" size="sm" className="mt-2 w-full" disabled={loadingMore === col.status} onClick={() => void loadMore(col)}>
                {loadingMore === col.status ? "Loading..." : `Load more (${col.count - col.leads.length})`}
              </Button>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
