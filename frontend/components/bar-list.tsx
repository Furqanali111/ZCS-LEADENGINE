import Link from "next/link";
import { useId } from "react";
import type { CountItem } from "@/lib/api";
import { PANEL_CLASS } from "@/lib/ui";

// One series, so one hue (dataviz slot 1). The count is always printed as text, so color carries nothing alone.
export function BarList({
  title,
  items,
  labels = {},
  hrefFor,
}: {
  title: string;
  items: CountItem[];
  labels?: Record<string, string>;
  hrefFor?: (key: string) => string;
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
          {items.map((i) => {
            const label = labels[i.key] ?? i.key;
            const row = (
              <>
                <span className="truncate" title={label}>
                  {label}
                </span>
                <span aria-hidden className="h-3 rounded-r-sm bg-muted">
                  <span className="block h-3 rounded-r-sm bg-chart-1" style={{ width: `${(i.count / max) * 100}%` }} />
                </span>
                <span className="text-right tabular-nums">{i.count.toLocaleString("en-US")}</span>
              </>
            );
            const cls = "grid grid-cols-[8rem_1fr_3rem] items-center gap-3 text-sm";
            return (
              <li key={i.key}>
                {hrefFor ? (
                  <Link
                    href={hrefFor(i.key)}
                    aria-label={`${label}: ${i.count.toLocaleString("en-US")} leads. View these leads`}
                    className={`${cls} -mx-2 rounded-md px-2 py-1 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring`}
                  >
                    {row}
                  </Link>
                ) : (
                  <div className={cls}>{row}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
