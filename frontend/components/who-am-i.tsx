"use client";

import { useState } from "react";
import { UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { setName, useName } from "@/lib/me";

// Top-right "working as" box. Leads are claimed under this name, so it is asked for before anything else.
export function WhoAmI() {
  const name = useName();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  if (name && !editing) {
    return (
      <div className="ml-auto flex shrink-0 items-center gap-2 text-sm">
        <UserRound aria-hidden className="size-4 text-muted-foreground" />
        <span className="font-medium">{name}</span>
        <Button variant="ghost" size="sm" onClick={() => { setDraft(name); setEditing(true); }}>
          Change
        </Button>
      </div>
    );
  }
  return (
    <form
      className="ml-auto flex shrink-0 items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setName(draft);
        setEditing(false);
      }}
    >
      <label htmlFor="who" className="sr-only">
        Your name
      </label>
      <Input id="who" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={40} placeholder="Your name to claim leads" className="h-9 w-52" />
      <Button type="submit" size="sm" disabled={!draft.trim()}>
        Save
      </Button>
    </form>
  );
}
