import { useSyncExternalStore } from "react";

// No accounts: each salesperson types their name once; it is kept in this browser and sent as X-Salesperson.
const KEY = "zcs_name";
const listeners = new Set<() => void>();

export function getName(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setName(name: string) {
  try {
    if (name.trim()) localStorage.setItem(KEY, name.trim().slice(0, 40));
    else localStorage.removeItem(KEY);
  } catch {
    // storage blocked: the name just will not persist
  }
  listeners.forEach((l) => l());
}

export function useName(): string {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    getName,
    () => "",
  );
}
