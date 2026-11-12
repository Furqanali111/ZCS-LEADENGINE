import { useEffect, useRef, useState } from "react";

async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // shortcut: older browsers or insecure origins, fall back to a hidden textarea
    const prev = document.activeElement as HTMLElement | null;
    const t = document.createElement("textarea");
    t.value = text;
    t.setAttribute("readonly", "");
    t.style.position = "fixed";
    t.style.opacity = "0";
    document.body.appendChild(t);
    t.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    t.remove();
    prev?.focus();
    return ok;
  }
}

// `copied` is the key of the last successful copy for 2 seconds; `failed` is the key of a failed one.
export function useCopy() {
  const [copied, setCopied] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy(key: string, text: string) {
    const ok = await writeClipboard(text);
    setCopied(ok ? key : null);
    setFailed(ok ? null : key);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setCopied(null);
      setFailed(null);
    }, 2000);
  }
  return { copied, failed, copy };
}
