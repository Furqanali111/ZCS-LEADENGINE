"use client";

import { ArrowRightLeft, Check, GripVertical } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { priorityTone, ToneBadge } from "@/components/tone-badge";
import { isOverdue } from "@/lib/dates";
import { formatDay } from "@/lib/format";
import { CRM_STATUSES, PRIORITIES } from "@/lib/constants";
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
  const [open, setOpen] = useState(false);
  // Fixed position so the menu is not clipped by the board's horizontal scroll area.
  const [pos, setPos] = useState<{ right: number; top?: number; bottom?: number }>({ right: 0 });
  const wrap = useRef<HTMLDivElement>(null);
  const overdue = isOverdue(card.next_follow_up_at);
  const place = [card.city, card.state].filter(Boolean).join(", ");
  const priority = PRIORITIES.find((p) => p.value === card.priority)?.label;
  const items = () => Array.from(wrap.current?.querySelectorAll<HTMLButtonElement>("[role=menuitemradio]") ?? []);
  const focusTrigger = () => document.getElementById(`move-${card.id}`)?.focus();

  useEffect(() => {
    if (!open) return;
    (items().find((b) => b.getAttribute("aria-checked") === "true") ?? items()[0])?.focus();
    const away = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const close = () => setOpen(false);
    document.addEventListener("mousedown", away);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", away);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  function openMenu() {
    const r = document.getElementById(`move-${card.id}`)?.getBoundingClientRect();
    if (r) {
      const right = window.innerWidth - r.right;
      // Menu is about 360px tall: open upward when there is no room below.
      setPos(r.bottom + 368 > window.innerHeight && r.top > 368 ? { right, bottom: window.innerHeight - r.top } : { right, top: r.bottom });
    }
    setOpen(true);
  }

  function onMenuKey(e: React.KeyboardEvent) {
    const list = items();
    const i = list.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      focusTrigger();
    } else if (e.key === "ArrowDown" && !open && !busy) {
      e.preventDefault();
      openMenu();
    } else if (!open) {
      return;
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      list[(i + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length]?.focus();
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      list[e.key === "Home" ? 0 : list.length - 1]?.focus();
    } else if (e.key === "Tab") setOpen(false);
  }

  return (
    <li
      draggable={!busy}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", JSON.stringify({ id: card.id, from: status }));
        e.dataTransfer.effectAllowed = "move";
      }}
      className={`relative rounded-lg border bg-card p-3 text-sm shadow-xs transition-shadow hover:shadow-sm ${busy ? "opacity-60" : "cursor-grab active:cursor-grabbing"}`}
    >
      <div className="flex items-start gap-1">
        <GripVertical aria-hidden className="mt-0.5 -ml-1 size-4 shrink-0 text-muted-foreground/60" />
        <Link href={`/leads/${card.id}`} className="min-w-0 flex-1 rounded-sm font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          {card.name}
        </Link>
        <div ref={wrap} onKeyDown={onMenuKey} className="-mt-1 -mr-1.5 shrink-0">
          <button
            type="button"
            id={`move-${card.id}`}
            aria-disabled={busy}
            aria-haspopup="menu"
            aria-expanded={open}
            aria-label={`Move ${card.name} to another status`}
            onClick={() => (open ? setOpen(false) : busy ? undefined : openMenu())}
            className={`flex size-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${busy ? "opacity-50" : ""}`}
          >
            <ArrowRightLeft aria-hidden className="size-4" />
          </button>
          {open && (
            <div role="menu" aria-label={`Move ${card.name} to`} style={pos} className="fixed z-50 w-44 cursor-default rounded-lg border bg-popover p-1 text-popover-foreground shadow-md">
              {CRM_STATUSES.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  role="menuitemradio"
                  title={s.hint}
                  aria-checked={s.value === status}
                  onClick={() => {
                    setOpen(false);
                    focusTrigger(); // the clicked item unmounts, so put focus back on Move now
                    if (s.value !== status) onMove(card, s.value);
                  }}
                  className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted focus-visible:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {s.label}
                  {s.value === status && <Check aria-hidden className="size-4" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <p className="mt-0.5 text-muted-foreground">{place || "No location"}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        {priority && <ToneBadge tone={priorityTone(card.priority)}>{priority}</ToneBadge>}
        <span className="tabular-nums">Score {card.fit_score ?? "-"}</span>
        {card.owner && <ToneBadge tone="warning">{card.owner}</ToneBadge>}
      </div>
      {card.next_follow_up_at && (
        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
          <span className={overdue ? "font-medium text-tone-danger-fg" : "text-muted-foreground"}>Follow-up {formatDay(card.next_follow_up_at)}</span>
          {overdue && <ToneBadge tone="danger">Overdue</ToneBadge>}
        </p>
      )}
    </li>
  );
}
