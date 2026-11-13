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

// Ask for a name before an action that is recorded under it. Resolves true when a name exists or was just saved, false when cancelled.
let waiting: ((ok: boolean) => void) | null = null;
const askListeners = new Set<(open: boolean) => void>();

export function requireName(): Promise<boolean> {
  if (getName()) return Promise.resolve(true);
  waiting?.(false); // a second request replaces a prompt nobody answered
  return new Promise((resolve) => {
    waiting = resolve;
    askListeners.forEach((l) => l(true));
  });
}

export function answerNamePrompt(ok: boolean) {
  waiting?.(ok);
  waiting = null;
  askListeners.forEach((l) => l(false));
}

export function onNamePrompt(cb: (open: boolean) => void) {
  askListeners.add(cb);
  return () => {
    askListeners.delete(cb);
  };
}
