import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type Tone = "danger" | "warning" | "success" | "info" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  danger: "bg-tone-danger-bg text-tone-danger-fg",
  warning: "bg-tone-warning-bg text-tone-warning-fg",
  success: "bg-tone-success-bg text-tone-success-fg",
  info: "bg-tone-info-bg text-tone-info-fg",
  neutral: "bg-tone-neutral-bg text-tone-neutral-fg",
};

// Decorative dot beside a status; the text label stays the accessible value.
export const TONE_DOT: Record<Tone, string> = {
  danger: "bg-tone-danger-fg",
  warning: "bg-tone-warning-fg",
  success: "bg-tone-success-fg",
  info: "bg-tone-info-fg",
  neutral: "bg-muted-foreground",
};

const PRIORITY_TONE: Record<string, Tone> = { critical: "danger", high: "warning", medium: "info", low: "neutral" };

const STATUS_TONE: Record<string, Tone> = {
  new: "info",
  researching: "neutral",
  email_sent: "info",
  called: "info",
  follow_up_required: "warning",
  interested: "success",
  meeting_scheduled: "success",
  not_interested: "neutral",
  converted: "success",
  do_not_contact: "danger",
};

export const priorityTone = (v: string | null | undefined): Tone => PRIORITY_TONE[v ?? ""] ?? "neutral";
export const statusTone = (v: string | null | undefined): Tone => STATUS_TONE[v ?? ""] ?? "neutral";

// The label always carries the meaning; the dot and tint only reinforce it.
export function ToneBadge({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  return (
    <Badge variant="secondary" className={cn("gap-1.5", TONE_CLASS[tone], className)}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {children}
    </Badge>
  );
}
