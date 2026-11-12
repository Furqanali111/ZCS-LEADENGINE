import { useId } from "react";
import type { CountItem } from "@/lib/api";
import { PANEL_CLASS } from "@/lib/ui";

// One series, so one hue (dataviz slot 1). The count is always printed as text, so color carries nothing alone.
export function BarList({
  title,
  items,
  labels = {},
}: {
  title: string;
  items: CountItem[];
  labels?: Record<string, string>;
}) {
  const id = useId();
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <section aria-labelledby={id} className={PANEL_CLASS}>
      <h2 id={id} className="mb-3 text-sm font-semibold">{title}</h2>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No data yet.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((i) => (
            <li key={i.key} className="grid grid-cols-[8rem_1fr_3rem] items-center gap-3 text-sm">
              <span className="truncate" title={labels[i.key] ?? i.key}>
                {labels[i.key] ?? i.key}
              </span>
              <span aria-hidden className="h-3 rounded-r-sm bg-muted">
                <span
                  className="block h-3 rounded-r-sm bg-chart-1"
                  style={{ width: `${(i.count / max) * 100}%` }}
                />
              </span>
              <span className="text-right tabular-nums">{i.count.toLocaleString("en-US")}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
