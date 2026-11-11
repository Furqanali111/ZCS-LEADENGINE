export function formatPhone(raw: string | null): string {
  if (!raw) return "-";
  const d = raw.replace(/\D/g, "");
  const n = d.length === 11 && d.startsWith("1") ? d.slice(1) : d;
  return n.length === 10 ? `(${n.slice(0, 3)}) ${n.slice(3, 6)}-${n.slice(6)}` : raw;
}

// Only http(s) URLs become links; anything else renders as plain text.
export const safeHttpUrl = (u: string | null | undefined) => {
  try {
    return u && /^https?:$/.test(new URL(u).protocol) ? u : null;
  } catch {
    return null;
  }
};

export const hostOf = (u: string) => {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return u;
  }
};
