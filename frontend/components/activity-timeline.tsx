import { Button } from "@/components/ui/button";
import type { Activity } from "@/lib/api";
import { ACTIVITY_TYPES, CRM_STATUSES, OUTCOMES } from "@/lib/constants";

const status = (v: string | null) => CRM_STATUSES.find((s) => s.value === v)?.label ?? v ?? "none";

export function ActivityTimeline({
  items,
  total,
  loading,
  onMore,
}: {
  items: Activity[];
  total: number;
  loading: boolean;
  onMore: () => void;
}) {
  if (total === 0) return <p className="text-sm text-muted-foreground">No activity yet. Log the first call, email or note above.</p>;
  return (
    <div className="space-y-3">
      <ol aria-label="Activity timeline, newest first" className="space-y-3">
        {items.map((a) => {
          const label = ACTIVITY_TYPES.find((t) => t.value === a.type)?.label ?? a.type;
          const outcome = OUTCOMES.find((o) => o.value === a.outcome)?.label;
          return (
            <li key={a.id} className="rounded-lg border p-3 text-sm">
              <p className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{label}</span>
                {outcome && <span className="text-muted-foreground">{outcome}</span>}
                <time dateTime={a.occurred_at} className="ml-auto tabular-nums text-muted-foreground">
                  {new Date(a.occurred_at).toLocaleString()}
                </time>
              </p>
              {a.type === "status_change" && (
                <p>
                  Status changed from {status(a.from_status)} to {status(a.to_status)}
                </p>
              )}
              {a.summary && <p className="mt-1 whitespace-pre-wrap">{a.summary}</p>}
            </li>
          );
        })}
      </ol>
      <div className="flex items-center gap-3 text-sm">
        <p>
          Showing {items.length} of {total}
        </p>
        {items.length < total && (
          <Button variant="outline" size="sm" disabled={loading} onClick={onMore}>
            {loading ? "Loading..." : "Load more"}
          </Button>
        )}
      </div>
    </div>
  );
}
