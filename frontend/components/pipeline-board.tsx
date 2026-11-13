"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { PipelineCard } from "@/components/pipeline-card";
import { Button } from "@/components/ui/button";
import { requireName } from "@/lib/me";
import { ApiError, getPipeline, getPipelineColumn, patchLead, type PipelineCard as Card, type PipelineColumn } from "@/lib/api";
import { statusTone, TONE_DOT as DOT } from "@/components/tone-badge";
import { CRM_STATUSES } from "@/lib/constants";

const LABELS = Object.fromEntries(CRM_STATUSES.map((s) => [s.value, s.label]));
const msg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed");

export function PipelineBoard() {
  const [cols, setCols] = useState<PipelineColumn[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [over, setOver] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const serverOffset = useRef<Record<string, number>>({});

  useEffect(() => {
    getPipeline().then(
      (r) => {
        serverOffset.current = Object.fromEntries(r.columns.map((c) => [c.status, c.leads.length]));
        setCols(r.columns);
      },
      (e) => setError(msg(e)),
    );
  }, []);

  const move = useCallback(async (card: Card, from: string, to: string) => {
    if (from === to || !(await requireName())) return;
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
      const saved = await patchLead(card.id, { crm_status: to });
      setCols((cs) => cs && cs.map((c) => (c.status === to ? { ...c, leads: c.leads.map((l) => (l.id === card.id ? { ...l, owner: saved.owner } : l)) } : c))); // the server may have set the owner
      // The card left `from`, so the next page there starts one lead earlier.
      serverOffset.current[from] = Math.max(0, (serverOffset.current[from] ?? 0) - 1);
      setNotice(`Moved ${card.name} to ${LABELS[to]}`);
      // Refocus after React commits the card in its new column.
      setTimeout(() => document.getElementById(`move-${card.id}`)?.focus(), 0);
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
      setTimeout(() => document.getElementById(`move-${card.id}`)?.focus(), 0);
      setBusy((b) => {
        const n = new Set(b);
        n.delete(card.id);
        return n;
      });
      return;
    }
    setBusy((b) => {
      const n = new Set(b);
      n.delete(card.id);
      return n;
    });
    // Counts only (limit 1): keeps loaded cards. If this fails, the optimistic counts stay.
    try {
      const [a, b] = await Promise.all([getPipelineColumn(from, 0, 1), getPipelineColumn(to, 0, 1)]);
      setCols((cs) => cs && cs.map((c) => (c.status === from ? { ...c, count: a.count } : c.status === to ? { ...c, count: b.count } : c)));
    } catch {
      // Move already saved; optimistic counts are kept.
    }
  }, []);

  async function loadMore(col: PipelineColumn) {
    setLoadingMore(col.status);
    try {
      // Server-side offset: local moves change leads.length but not what the server has served.
      const offset = serverOffset.current[col.status] ?? col.leads.length;
      const r = await getPipelineColumn(col.status, offset);
      serverOffset.current[col.status] = (serverOffset.current[col.status] ?? offset) + r.leads.length; // add, so a move during the request is kept
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
      <p role="status" className="sr-only">{notice}</p>
      {error && (
        <p role="alert" className="mb-3 rounded-lg border border-destructive/40 bg-tone-danger-bg px-3 py-2 text-sm text-tone-danger-fg">
          {error}
        </p>
      )}
      <div className="grid min-h-[26rem] auto-cols-[minmax(13.5rem,1fr)] grid-flow-col items-start gap-3 overflow-x-auto pb-3">
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
            className={`min-w-0 rounded-xl border bg-muted/50 p-2 transition-shadow ${over === col.status ? "ring-2 ring-ring" : ""}`}
          >
            <h2 id={`col-${col.status}`} className="mb-2 flex items-center gap-2 px-1 text-sm font-semibold">
              <span aria-hidden className={`size-2 shrink-0 rounded-full ${DOT[statusTone(col.status)]}`} />
              {LABELS[col.status] ?? col.status}
              <Link
                href={`/leads?crm_status=${col.status}`}
                aria-label={`View all ${col.count} ${LABELS[col.status] ?? col.status} leads in the leads list`}
                className="ml-auto rounded-full bg-background px-2 py-0.5 text-xs font-medium tabular-nums text-muted-foreground underline-offset-2 hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {col.count}
              </Link>
            </h2>
            <ul className="flex min-h-12 flex-col gap-2">
              {col.leads.map((card) => (
                <PipelineCard key={card.id} card={card} status={col.status} busy={busy.has(card.id)} onMove={(c, to) => void move(c, col.status, to)} />
              ))}
            </ul>
            {col.leads.length === 0 && <p className="rounded-lg border border-dashed px-2 py-4 text-center text-xs text-muted-foreground">No leads</p>}
            {col.leads.length < col.count && (
              <Button variant="outline" size="sm" className="mt-2 w-full" disabled={loadingMore === col.status} onClick={() => void loadMore(col)}>
                {loadingMore === col.status ? "Loading..." : `Show more (${col.leads.length} of ${col.count} shown)`}
              </Button>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
