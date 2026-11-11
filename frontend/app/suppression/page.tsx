"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError, addSuppression, listSuppression, removeSuppression, type SuppressionEntry } from "@/lib/api";
import { SUPPRESSION_KINDS } from "@/lib/constants";

const SELECT =
  "mt-1 h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";
const ERROR = "text-sm text-red-700 dark:text-red-400";

export default function SuppressionPage() {
  const [entries, setEntries] = useState<SuppressionEntry[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [kind, setKind] = useState("npi");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  const h1Ref = useRef<HTMLHeadingElement>(null);
  const confirmBtn = useRef<HTMLButtonElement>(null);
  const removeBtns = useRef(new Map<string, HTMLButtonElement>());
  const restoreId = useRef<string | null>(null);

  useEffect(() => {
    if (confirmId) confirmBtn.current?.focus();
    else if (restoreId.current) {
      removeBtns.current.get(restoreId.current)?.focus();
      restoreId.current = null;
    }
  }, [confirmId]);

  const load = useCallback(() => {
    listSuppression()
      .then((d) => {
        setEntries(d);
        setLoadError(null);
      })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Could not load the suppression list."));
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) {
      setFormError("Enter a value to suppress.");
      return;
    }
    setSaving(true);
    setFormError(null);
    setMessage(null);
    try {
      await addSuppression({ kind, value: value.trim(), reason: reason.trim() || undefined });
      setValue("");
      setReason("");
      setMessage({ text: "Entry added.", error: false });
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not add the entry.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(entry: SuppressionEntry) {
    try {
      await removeSuppression(entry.id);
      setMessage({ text: `Removed ${entry.value}.`, error: false });
      h1Ref.current?.focus();
      load();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not remove the entry.", error: true });
    } finally {
      setConfirmId(null);
    }
  }

  return (
    <div className="space-y-6">
      <h1 ref={h1Ref} tabIndex={-1} className="text-xl font-semibold outline-none">Suppression list</h1>
      <p className="text-sm text-muted-foreground">
        Suppressed NPIs and phone numbers are marked on matching leads and never reset by a new search. Email entries are stored now and take effect
        when emails are collected.
      </p>

      <form onSubmit={add} aria-label="Add suppression entry" className="grid gap-3 sm:grid-cols-[8rem_1fr_1fr_auto] sm:items-end">
        <div>
          <Label htmlFor="s-kind">Kind</Label>
          <select id="s-kind" className={SELECT} value={kind} onChange={(e) => setKind(e.target.value)}>
            {SUPPRESSION_KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="s-value">Value</Label>
          <Input
            id="s-value"
            className="mt-1"
            value={value}
            aria-invalid={!!formError}
            aria-describedby={formError ? "s-error" : undefined}
            onChange={(e) => setValue(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="s-reason">Reason (optional)</Label>
          <Input id="s-reason" className="mt-1" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <Button type="submit" disabled={saving}>
          {saving ? "Adding..." : "Add entry"}
        </Button>
        {kind === "email" && (
          <p className="text-sm text-muted-foreground sm:col-span-4">
            Email entries are stored now and start blocking when emails are collected (a later slice).
          </p>
        )}
        {formError && (
          <p id="s-error" role="alert" className={`${ERROR} sm:col-span-4`}>
            {formError}
          </p>
        )}
      </form>

      <div role="status" aria-live="polite" className={message?.error ? ERROR : "text-sm text-muted-foreground"}>
        {message?.text}
      </div>

      {loadError ? (
        <p role="alert" className={ERROR}>
          {loadError}
        </p>
      ) : !entries ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No suppression entries.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kind</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Added</TableHead>
              <TableHead>Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((en) => (
              <TableRow key={en.id}>
                <TableCell>{SUPPRESSION_KINDS.find((k) => k.value === en.kind)?.label ?? en.kind}</TableCell>
                <TableCell className="tabular-nums">{en.value}</TableCell>
                <TableCell className="whitespace-normal">{en.reason ?? "-"}</TableCell>
                <TableCell className="whitespace-nowrap">{new Date(en.created_at).toLocaleDateString()}</TableCell>
                <TableCell>
                  {confirmId === en.id ? (
                    <span className="flex items-center gap-2">
                      <Button ref={confirmBtn} variant="destructive" size="sm" onClick={() => remove(en)}>
                        Confirm remove
                        <span className="sr-only"> {en.value}</span>
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          restoreId.current = en.id;
                          setConfirmId(null);
                        }}
                      >
                        Cancel
                      </Button>
                    </span>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      ref={(el) => {
                        if (el) removeBtns.current.set(en.id, el);
                        else removeBtns.current.delete(en.id);
                      }}
                      onClick={() => setConfirmId(en.id)}
                    >
                      Remove
                      <span className="sr-only"> {en.value}</span>
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
