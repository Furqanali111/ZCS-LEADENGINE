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

export function StatTile({ label, value, hint, Icon, tone = "blue" }: { label: string; value: number; hint?: string; Icon?: LucideIcon; tone?: StatTone }) {
  return (
    <div className={`flex items-start justify-between gap-3 rounded-2xl bg-gradient-to-br p-5 text-white shadow-sm ${TONES[tone]}`}>
      <div className="min-w-0">
        <dt className="text-sm font-medium text-white/90">{label}</dt>
        <dd className="mt-1 text-4xl font-semibold tracking-tight tabular-nums">{value.toLocaleString("en-US")}</dd>
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
