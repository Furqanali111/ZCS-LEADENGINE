"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Download } from "lucide-react";
import { LeadFilters } from "@/components/lead-filters";
import { LeadsTable } from "@/components/leads-table";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { ApiError, exportLeadsFile, listLeads, type LeadFilters as Filters, type LeadPage } from "@/lib/api";
import { CRM_STATUSES, ORG_TYPES, PRIORITIES, US_STATES } from "@/lib/constants";

const PAGE_SIZE = 50;
const FILTER_KEYS = ["q", "state", "specialty", "organization_type", "priority", "min_score", "crm_status", "search_job_id", "follow_up", "has_website", "has_email"] as const;
const ALLOWED: Record<string, Set<string>> = {
  state: new Set(US_STATES.map((s) => s.code)),
  priority: new Set(PRIORITIES.map((p) => p.value)),
  crm_status: new Set(CRM_STATUSES.map((s) => s.value)),
  organization_type: new Set(ORG_TYPES.map((o) => o.value)),
  follow_up: new Set(["due", "overdue", "none"]),
  has_website: new Set(["true"]),
  has_email: new Set(["true"]),
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function LeadsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  // Invalid URL values are ignored, never sent to the API.
  const filters = useMemo(() => {
    const f: Record<string, string | number> = {};
    for (const k of FILTER_KEYS) {
      const v = params.get(k);
      if (!v) continue;
      if (k === "min_score") {
        if (/^\d{1,3}$/.test(v) && Number(v) <= 100) f[k] = Number(v);
      } else if (k in ALLOWED ? ALLOWED[k].has(v) : k === "search_job_id" ? UUID.test(v) : true) f[k] = v;
    }
    return f as Filters;
  }, [params]);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const sortParam = params.get("sort");
  const sort = sortParam === "name" || sortParam === "follow_up" ? sortParam : "score";
  const order = params.get("order") === "asc" ? "asc" : "desc";

  // Every filter, sort and page change goes through the URL, so a refresh keeps it. Page resets unless given.
  const update = useCallback(
    (changes: Record<string, string | undefined>) => {
      // Read the live URL, not the render-time params, so delayed (debounced) calls never drop other filters.
      const next = new URLSearchParams(window.location.search);
      for (const [k, v] of Object.entries(changes)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      if (!("page" in changes)) next.delete("page");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
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
  const data = current?.data ?? result?.data ?? null; // keep the previous page visible while the next one loads
  const loading = !current;

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
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage({ text: `Exported ${selected.size > 0 ? selected.size : total} leads to ${filename}.`, error: false });
    } catch (e) {
      setMessage({ text: e instanceof ApiError ? e.message : "Export failed.", error: true });
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Leads"
        description={data ? `${total.toLocaleString("en-US")} ${total === 1 ? "lead" : "leads"} match the current filters.` : undefined}
        actions={
          <Button onClick={doExport} disabled={exporting || total === 0}>
            <Download aria-hidden />
            {exporting ? "Exporting..." : selected.size > 0 ? `Export selected (${selected.size})` : `Export filtered (${total})`}
          </Button>
        }
      />
      <LeadFilters
        filters={filters}
        onChange={update}
        onClear={() => {
          router.replace(pathname, { scroll: false });
        }}
      />
      <div role="status" aria-live="polite" className={message?.error ? "text-sm text-destructive" : "text-sm text-muted-foreground empty:hidden"}>
        {message?.text}
      </div>
      {current?.error ? (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-tone-danger-bg px-3 py-2 text-sm text-tone-danger-fg">
          {current.error}
        </p>
      ) : !data ? (
        <p className="text-sm text-muted-foreground">Loading leads...</p>
      ) : (
        <div aria-busy={loading} className={loading ? "opacity-70 transition-opacity" : "transition-opacity"}>
          <LeadsTable
            data={data}
            sort={sort}
            order={order}
            pageSize={PAGE_SIZE}
            selected={selected}
            onSelect={setSelected}
            onSort={(col) => update({ sort: col, order: col === sort ? (order === "asc" ? "desc" : "asc") : col === "name" || col === "follow_up" ? "asc" : "desc" })}
            onPage={(p) => update({ page: p > 1 ? String(p) : undefined })}
            onMessage={(text, error) => setMessage({ text, error })}
          />
        </div>
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
