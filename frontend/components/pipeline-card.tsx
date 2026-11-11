"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { isOverdue } from "@/lib/dates";
import { CRM_STATUSES } from "@/lib/constants";
import type { PipelineCard as Card } from "@/lib/api";

export function PipelineCard({
  card,
  status,
  busy,
  onMove,
}: {
  card: Card;
  status: string;
  busy: boolean;
  onMove: (card: Card, to: string) => void;
}) {
  const overdue = isOverdue(card.next_follow_up_at);
  const place = [card.city, card.state].filter(Boolean).join(", ");
  return (
    <li
      draggable={!busy}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", JSON.stringify({ id: card.id, from: status }));
        e.dataTransfer.effectAllowed = "move";
      }}
      className={`rounded-lg border bg-card p-2.5 text-sm shadow-xs ${busy ? "opacity-60" : "cursor-grab active:cursor-grabbing"}`}
    >
      <Link href={`/leads/${card.id}`} className="font-medium underline-offset-4 hover:underline">
        {card.name}
      </Link>
      <p className="text-muted-foreground">{place || "No location"}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span>Score {card.fit_score ?? "-"}</span>
        {card.next_follow_up_at && (
          <span className={overdue ? "font-medium text-destructive" : "text-muted-foreground"}>
            Follow-up {card.next_follow_up_at}
          </span>
        )}
        {overdue && <Badge variant="destructive">Overdue</Badge>}
      </div>
      <label className="mt-2 block text-xs text-muted-foreground">
        Move to
        <select
          id={`move-${card.id}`}
          aria-label={`Move ${card.name} to`}
          disabled={busy}
          value={status}
          onChange={(e) => onMove(card, e.target.value)}
          className="mt-0.5 h-7 w-full rounded-lg border border-input bg-transparent px-1.5 text-xs text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        >
          {CRM_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
    </li>
  );
}
