"use client";

import { GripVertical } from "lucide-react";
import Link from "next/link";
import { priorityTone, ToneBadge } from "@/components/tone-badge";
import { isOverdue } from "@/lib/dates";
import { CRM_STATUSES, PRIORITIES } from "@/lib/constants";
import { SELECT_CLASS } from "@/lib/ui";
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
  const priority = PRIORITIES.find((p) => p.value === card.priority)?.label;
  return (
    <li
      draggable={!busy}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", JSON.stringify({ id: card.id, from: status }));
        e.dataTransfer.effectAllowed = "move";
      }}
      className={`rounded-lg border bg-card p-3 text-sm shadow-xs transition-shadow hover:shadow-sm ${busy ? "opacity-60" : "cursor-grab active:cursor-grabbing"}`}
    >
      <div className="flex items-start gap-1">
        <GripVertical aria-hidden className="mt-0.5 -ml-1 size-4 shrink-0 text-muted-foreground/60" />
        <Link href={`/leads/${card.id}`} className="font-medium underline-offset-4 hover:underline">
          {card.name}
        </Link>
      </div>
      <p className="mt-0.5 text-muted-foreground">{place || "No location"}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        {priority && <ToneBadge tone={priorityTone(card.priority)}>{priority}</ToneBadge>}
        <span className="tabular-nums">Score {card.fit_score ?? "-"}</span>
      </div>
      {card.next_follow_up_at && (
        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
          <span className={overdue ? "font-medium text-tone-danger-fg" : "text-muted-foreground"}>Follow-up {card.next_follow_up_at}</span>
          {overdue && <ToneBadge tone="danger">Overdue</ToneBadge>}
        </p>
      )}
      <label className="mt-2.5 block text-xs text-muted-foreground">
        Move to
        <select
          id={`move-${card.id}`}
          aria-label={`Move ${card.name} to`}
          disabled={busy}
          value={status}
          onChange={(e) => onMove(card, e.target.value)}
          className={`${SELECT_CLASS} mt-0.5 h-7 text-xs text-foreground`}
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
