"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { listTemplates, type Lead, type OutreachTemplate } from "@/lib/api";
import { PANEL_CLASS, SELECT_CLASS, TEXTAREA_CLASS } from "@/lib/ui";
import { fillTemplate } from "@/lib/templates";


// Copy-only: fills a saved template from the lead in the browser. Nothing is ever sent.
export function LeadTemplates({ lead }: { lead: Lead }) {
  const [items, setItems] = useState<OutreachTemplate[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    listTemplates().then(setItems, () => setFailed(true));
  }, []);

  const t = items?.find((x) => x.id === selected);
  const contact = [lead.contact?.first_name, lead.contact?.last_name].filter(Boolean).join(" ");
  const values = { practice: lead.name, contact, city: lead.city ?? "", state: lead.state ?? "" };
  const text = t ? [t.subject ? `Subject: ${fillTemplate(t.subject, values)}\n` : "", fillTemplate(t.body, values)].join("\n").trim() : "";

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setStatus("Copied");
    } catch {
      setStatus("Could not copy. Select the text and copy it by hand.");
    }
  }

  return (
    <section aria-labelledby="tpl-h" className={PANEL_CLASS}>
      <h2 id="tpl-h" className="mb-2">
        Templates
      </h2>
      {failed ? (
        <p className="text-muted-foreground">Could not load templates.</p>
      ) : items && items.length === 0 ? (
        <p className="text-muted-foreground">No templates yet. Add one on the Templates page.</p>
      ) : (
        <div className="space-y-2">
          <Label htmlFor="tpl-select">Template</Label>
          <select
            id="tpl-select"
            className={SELECT_CLASS}
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setStatus("");
            }}
          >
            <option value="">Choose a template</option>
            {(items ?? []).map((x) => (
              <option key={x.id} value={x.id}>
                {x.name} ({x.kind})
              </option>
            ))}
          </select>
          {t && (
            <>
              <Label htmlFor="tpl-preview">Preview (read only)</Label>
              <textarea
                id="tpl-preview"
                readOnly
                rows={8}
                value={text}
                className={TEXTAREA_CLASS}
              />
              <Button variant="outline" size="sm" onClick={copy}>
                Copy
              </Button>
            </>
          )}
        </div>
      )}
      <p role="status" aria-live="polite" className="mt-1 min-h-5 text-muted-foreground">
        {status}
      </p>
    </section>
  );
}
