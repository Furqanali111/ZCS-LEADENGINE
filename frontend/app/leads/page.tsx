"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { LeadFilters } from "@/components/lead-filters";
import { LeadsTable } from "@/components/leads-table";
import { Button } from "@/components/ui/button";
import { ApiError, exportLeadsFile, listLeads, type LeadFilters as Filters, type LeadPage } from "@/lib/api";

const PAGE_SIZE = 50;
const FILTER_KEYS = ["q", "state", "specialty", "organization_type", "priority", "min_score", "crm_status", "search_job_id"] as const;

function LeadsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const filters = useMemo(() => {
    const f: Record<string, string | number> = {};
    for (const k of FILTER_KEYS) {
      const v = params.get(k);
      if (v) f[k] = k === "min_score" ? Number(v) : v;
    }
    return f as Filters;
  }, [params]);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const sort = params.get("sort") === "name" ? "name" : "score";
  const order = params.get("order") === "asc" ? "asc" : "desc";

  // Every filter, sort and page change goes through the URL, so a refresh keeps it. Page resets unless given.
  const update = useCallback(
    (changes: Record<string, string | undefined>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(changes)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      if (!("page" in changes)) next.delete("page");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const filterSig = JSON.stringify(filters);
  const lastSig = useRef(filterSig);
  useEffect(() => {
    if (lastSig.current === filterSig) return;
    lastSig.current = filterSig;
    const t = setTimeout(() => setSelected(new Set()), 0); // selection resets when filters change
    return () => clearTimeout(t);
  }, [filterSig]);

  // The result is keyed by its request, so "loading" is derived and no state is set synchronously in the effect.
  const reqKey = JSON.stringify({ filters, page, sort, order });
  const [result, setResult] = useState<{ key: string; data?: LeadPage; error?: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => {
      listLeads({ ...filters, page, page_size: PAGE_SIZE, sort, order })
        .then((data) => !cancelled && setResult({ key: reqKey, data }))
        .catch((e) => !cancelled && setResult({ key: reqKey, error: e instanceof ApiError ? e.message : "Could not load leads." }));
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
    // reqKey encodes every other input
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqKey]);
  const current = result?.key === reqKey ? result : null;
  const data = current?.data ?? null;

  const [exporting, setExporting] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const total = data?.total ?? 0;

  async function doExport() {
    setExporting(true);
    setMessage(null);
    try {
      const { blob, filename } = await exportLeadsFile(selected.size > 0 ? { ids: [...selected] } : { filters });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setMessage({ text: `Exported ${selected.size > 0 ? selected.size : total} leads to ${filename}.`, error: false });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.message : "Export failed.", error: true });
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Leads</h1>
        <Button onClick={doExport} disabled={exporting || total === 0}>
          {exporting ? "Exporting..." : selected.size > 0 ? `Export selected (${selected.size})` : `Export filtered (${total})`}
        </Button>
      </div>
      <LeadFilters
        filters={filters}
        onChange={update}
        onClear={() => {
          router.replace(pathname, { scroll: false });
        }}
      />
      <div role="status" aria-live="polite" className={message?.error ? "text-sm text-red-700 dark:text-red-400" : "text-sm text-muted-foreground"}>
        {message?.text}
      </div>
      {current?.error ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {current.error}
        </p>
      ) : !data ? (
        <p className="text-sm text-muted-foreground">Loading leads...</p>
      ) : (
        <LeadsTable
          data={data}
          sort={sort}
          order={order}
          pageSize={PAGE_SIZE}
          selected={selected}
          onSelect={setSelected}
          onSort={(col) => update({ sort: col, order: col === sort ? (order === "asc" ? "desc" : "asc") : col === "name" ? "asc" : "desc" })}
          onPage={(p) => update({ page: p > 1 ? String(p) : undefined })}
          onMessage={(text, error) => setMessage({ text, error })}
        />
      )}
    </div>
  );
}

export default function LeadsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading leads...</p>}>
      <LeadsView />
    </Suspense>
  );
}
