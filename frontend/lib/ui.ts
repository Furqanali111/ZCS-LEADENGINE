// Shared classes for native form controls (the app keeps native selects and textareas for behavior and accessibility).
const CONTROL =
  "w-full rounded-lg border border-input bg-surface px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive disabled:opacity-50 dark:bg-input/30";

export const SELECT_CLASS = `${CONTROL} h-8`;
export const TEXTAREA_CLASS = `${CONTROL} py-1.5`;
export const ERROR_CLASS = "text-sm text-destructive";
// Panels on the page background.
export const PANEL_CLASS = "rounded-xl border bg-card p-4 shadow-xs";
