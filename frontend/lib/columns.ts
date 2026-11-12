import { useMemo, useSyncExternalStore } from "react";

// Optional leads-table columns. Hidden keys are kept per browser; nothing is read during the first render.
export const OPTIONAL_COLUMNS = [
  { key: "specialty", label: "Specialty" },
  { key: "location", label: "City, state" },
  { key: "phone", label: "Phone" },
  { key: "contact", label: "Primary contact" },
  { key: "website", label: "Website" },
  { key: "email", label: "Email" },
  { key: "priority", label: "Priority" },
  { key: "owner", label: "Owner" },
  { key: "follow_up", label: "Follow-up" },
] as const;

const KEY = "zcs_hidden_columns";
const listeners = new Set<() => void>();

const read = () => {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
};

export function setColumnHidden(key: string, hide: boolean, current: Set<string>) {
  const next = new Set(current);
  if (hide) next.add(key);
  else next.delete(key);
  try {
    localStorage.setItem(KEY, JSON.stringify([...next]));
  } catch {
    // storage blocked: the choice just will not persist
  }
  listeners.forEach((l) => l());
}

export function useHiddenColumns(): Set<string> {
  const raw = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
    () => "",
  );
  return useMemo(() => {
    try {
      const v = JSON.parse(raw || "[]");
      return new Set<string>(Array.isArray(v) ? v.filter((k) => typeof k === "string") : []);
    } catch {
      return new Set<string>();
    }
  }, [raw]);
}
