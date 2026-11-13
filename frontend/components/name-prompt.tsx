"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { answerNamePrompt, onNamePrompt, setName } from "@/lib/me";

// Opens when someone changes a lead without a name set. Saving the name lets the change go ahead under it.
export function NamePrompt() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState("");

  useEffect(
    () =>
      onNamePrompt((open) => {
        const d = dialog.current;
        if (!d) return;
        if (open && !d.open) {
          setDraft("");
          d.showModal();
        } else if (!open && d.open) d.close();
      }),
    [],
  );

  return (
    <dialog
      ref={dialog}
      aria-labelledby="name-prompt-title"
      className="m-auto w-full max-w-sm rounded-lg border bg-background p-5 text-foreground shadow-lg backdrop:bg-black/40"
      onCancel={(e) => {
        e.preventDefault(); // Esc: close through the same path as Cancel
        answerNamePrompt(false);
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!draft.trim()) return;
          setName(draft);
          answerNamePrompt(true);
        }}
        className="space-y-3"
      >
        <h2 id="name-prompt-title" className="text-base font-semibold">
          Set your name first
        </h2>
        <p className="text-sm text-muted-foreground">Changes are recorded under your name, and a lead you move on becomes yours. Enter your name, then the change goes through.</p>
        <label htmlFor="name-prompt-input" className="sr-only">
          Your name
        </label>
        <Input id="name-prompt-input" autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={40} placeholder="Your name" />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => answerNamePrompt(false)}>
            Cancel
          </Button>
          <Button type="submit" disabled={!draft.trim()}>
            Save name and continue
          </Button>
        </div>
      </form>
    </dialog>
  );
}
