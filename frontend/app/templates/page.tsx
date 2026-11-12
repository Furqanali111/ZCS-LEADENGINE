"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, createTemplate, deleteTemplate, listTemplates, updateTemplate, type OutreachTemplate } from "@/lib/api";

const SELECT =
  "mt-1 h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";
const TEXTAREA =
  "mt-1 w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";
const ERROR = "text-sm text-red-700 dark:text-red-400";

export default function TemplatesPage() {
  const [items, setItems] = useState<OutreachTemplate[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"email" | "call">("email");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const h1Ref = useRef<HTMLHeadingElement>(null);

  const load = useCallback(() => {
    listTemplates()
      .then((d) => {
        setItems(d);
        setLoadError(null);
      })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : "Could not load the templates."));
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  function reset() {
    setEditId(null);
    setName("");
    setKind("email");
    setSubject("");
    setBody("");
    setFormError(null);
  }

  function edit(t: OutreachTemplate) {
    setEditId(t.id);
    setName(t.name);
    setKind(t.kind);
    setSubject(t.subject ?? "");
    setBody(t.body);
    setFormError(null);
    nameRef.current?.focus();
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !body.trim()) {
      setFormError("Name and body are required.");
      return;
    }
    const input = { name: name.trim(), kind, subject: kind === "email" ? subject.trim() || null : null, body };
    setSaving(true);
    setFormError(null);
    try {
      if (editId) await updateTemplate(editId, input);
      else await createTemplate(input);
      setMessage({ text: editId ? "Template saved." : "Template added.", error: false });
      reset();
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not save the template.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(t: OutreachTemplate) {
    if (!window.confirm(`Delete the template "${t.name}"?`)) return;
    try {
      await deleteTemplate(t.id);
      if (editId === t.id) reset();
      setMessage({ text: `Deleted ${t.name}.`, error: false });
      h1Ref.current?.focus();
      load();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not delete the template.", error: true });
    }
  }

  return (
    <div className="space-y-6">
      <h1 ref={h1Ref} tabIndex={-1} className="text-xl font-semibold outline-none">Outreach templates</h1>
      <p className="text-sm text-muted-foreground">Placeholders: {"{practice}, {contact}, {city}, {state}"}. Nothing is ever sent from this tool.</p>

      <form onSubmit={save} aria-label={editId ? "Edit template" : "Add template"} className="grid gap-3 sm:grid-cols-[1fr_8rem]">
        <div>
          <Label htmlFor="t-name">Name</Label>
          <Input id="t-name" ref={nameRef} className="mt-1" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="t-kind">Kind</Label>
          <select id="t-kind" className={SELECT} value={kind} onChange={(e) => setKind(e.target.value as "email" | "call")}>
            <option value="email">Email</option>
            <option value="call">Call script</option>
          </select>
        </div>
        {kind === "email" && (
          <div className="sm:col-span-2">
            <Label htmlFor="t-subject">Subject (optional)</Label>
            <Input id="t-subject" className="mt-1" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
        )}
        <div className="sm:col-span-2">
          <Label htmlFor="t-body">Body</Label>
          <textarea
            id="t-body"
            className={TEXTAREA}
            rows={8}
            maxLength={5000}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            aria-describedby="t-hint"
          />
          <p id="t-hint" className="mt-1 text-xs text-muted-foreground">Business wording only. No patient information.</p>
        </div>
        {formError && (
          <p role="alert" className={`${ERROR} sm:col-span-2`}>
            {formError}
          </p>
        )}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving..." : editId ? "Save template" : "Add template"}
          </Button>
          {editId && (
            <Button type="button" variant="outline" onClick={reset}>
              Cancel edit
            </Button>
          )}
        </div>
      </form>

      <div role="status" aria-live="polite" className={message?.error ? ERROR : "text-sm text-muted-foreground"}>
        {message?.text}
      </div>

      {loadError ? (
        <p role="alert" className={ERROR}>
          {loadError}
        </p>
      ) : !items ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No templates yet.</p>
      ) : (
        <ul className="space-y-4">
          {items.map((t) => (
            <li key={t.id} className="space-y-1 rounded-lg border p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-semibold">{t.name}</h2>
                <Badge variant="outline">{t.kind === "email" ? "Email" : "Call script"}</Badge>
                <span className="ml-auto flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => edit(t)}>
                    Edit<span className="sr-only"> {t.name}</span>
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => remove(t)}>
                    Delete<span className="sr-only"> {t.name}</span>
                  </Button>
                </span>
              </div>
              {t.subject && <p><span className="font-medium">Subject:</span> {t.subject}</p>}
              <p className="whitespace-pre-wrap text-muted-foreground">{t.body}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
