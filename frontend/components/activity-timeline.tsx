import { ArrowRightLeft, CalendarDays, Flag, Mail, Phone, StickyNote, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Activity } from "@/lib/api";
import { ACTIVITY_TYPES, CRM_STATUSES, OUTCOMES } from "@/lib/constants";

const status = (v: string | null) => CRM_STATUSES.find((s) => s.value === v)?.label ?? v ?? "none";

const ICONS: Record<string, LucideIcon> = {
  call: Phone,
  email: Mail,
  meeting: CalendarDays,
  note: StickyNote,
  status_change: ArrowRightLeft,
  outcome: Flag,
};

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
  if (total === 0) return <p className="text-sm text-muted-foreground">No activity yet.</p>;
  return (
    <div className="space-y-4">
      <ol aria-label="Activity timeline, newest first" className="relative space-y-4 before:absolute before:inset-y-2 before:left-3.5 before:w-px before:bg-border">
        {items.map((a) => {
          const label = ACTIVITY_TYPES.find((t) => t.value === a.type)?.label ?? a.type;
          const outcome = OUTCOMES.find((o) => o.value === a.outcome)?.label;
          const Icon = ICONS[a.type] ?? StickyNote;
          return (
            <li key={a.id} className="relative flex gap-3 text-sm">
              <span aria-hidden className="z-10 grid size-7 shrink-0 place-items-center rounded-full border bg-card text-muted-foreground">
                <Icon className="size-3.5" />
              </span>
              <div className="min-w-0 flex-1 rounded-lg bg-muted/50 px-3 py-2">
                <p className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-medium">{label}</span>
                  {outcome && <span className="text-muted-foreground">{outcome}</span>}
                  {a.actor && <span className="text-muted-foreground">by {a.actor}</span>}
                  <time dateTime={a.occurred_at} className="ml-auto text-xs tabular-nums text-muted-foreground">
                    {new Date(a.occurred_at).toLocaleString()}
                  </time>
                </p>
                {a.type === "status_change" && (
                  <p>
                    Status changed from {status(a.from_status)} to {status(a.to_status)}
                  </p>
                )}
                {a.summary && <p className="mt-1 whitespace-pre-wrap">{a.summary}</p>}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="flex items-center gap-3 text-sm">
        <p className="text-muted-foreground">
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
