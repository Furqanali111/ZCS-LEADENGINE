// Local calendar date as YYYY-MM-DD (not UTC), matching how the backend defines "today".
export function todayLocal(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const isOverdue = (date: string | null): boolean => !!date && date < todayLocal();
