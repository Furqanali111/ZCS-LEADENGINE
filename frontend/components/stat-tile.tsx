import Link from "next/link";
import type { LucideIcon } from "lucide-react";

// Solid colors dark enough for white text at 4.5:1; the icon is decoration only.
const TONES = {
  blue: "from-primary to-blue-900",
  green: "from-emerald-700 to-emerald-900",
  orange: "from-orange-700 to-orange-900",
  red: "from-red-600 to-red-800",
  purple: "from-purple-600 to-purple-800",
  teal: "from-teal-700 to-teal-900",
} as const;

export type StatTone = keyof typeof TONES;

export function StatTile({ label, value, hint, Icon, tone = "blue", href }: { label: string; value: number; hint?: string; Icon?: LucideIcon; tone?: StatTone; href?: string }) {
  const n = value.toLocaleString("en-US");
  return (
    <div
      className={`relative flex items-start justify-between gap-3 rounded-2xl bg-gradient-to-br p-5 text-white shadow-sm ${TONES[tone]} ${href ? "transition hover:-translate-y-0.5 hover:shadow-md focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2" : ""}`}
    >
      <div className="min-w-0">
        <dt className="text-sm font-medium text-white/90">
          {href ? (
            // Stretched link: the whole tile is the click target, the label is the accessible name.
            <Link href={href} aria-label={`${label}: ${n}. View these leads`} className="outline-none after:absolute after:inset-0 after:rounded-2xl">
              {label}
            </Link>
          ) : (
            label
          )}
        </dt>
        <dd className="mt-1 text-4xl font-semibold tracking-tight tabular-nums">{n}</dd>
        {hint && <p className="mt-1 text-sm text-white/90">{hint}</p>}
      </div>
      {Icon && (
        <span aria-hidden className="grid size-12 shrink-0 place-items-center rounded-full bg-white/20">
          <Icon className="size-6" />
        </span>
      )}
    </div>
  );
}

export function StatTileSkeleton() {
  return <div aria-hidden className="h-[7.5rem] animate-pulse rounded-2xl bg-muted" />;
}
