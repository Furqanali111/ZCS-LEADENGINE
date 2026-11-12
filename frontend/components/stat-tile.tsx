import type { LucideIcon } from "lucide-react";
import { PANEL_CLASS } from "@/lib/ui";

// A plain number with its label; the icon is decoration only.
export function StatTile({ label, value, Icon }: { label: string; value: number; Icon?: LucideIcon }) {
  return (
    <div className={PANEL_CLASS}>
      <dt className="flex items-center gap-2 text-sm text-muted-foreground">
        {Icon && <Icon aria-hidden className="size-4 shrink-0" />}
        {label}
      </dt>
      <dd className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">{value.toLocaleString("en-US")}</dd>
    </div>
  );
}
