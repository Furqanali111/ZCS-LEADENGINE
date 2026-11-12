"use client";

import { useEffect, useRef, useState } from "react";
import { UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { setName, useName } from "@/lib/me";

// Top-right "working as" box. Leads are claimed under this name, so it is asked for before anything else.
export function WhoAmI() {
  const name = useName();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saved, setSaved] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const changeRef = useRef<HTMLButtonElement>(null);
  const move = useRef<"input" | "change" | null>(null); // where focus goes after the next swap

  useEffect(() => {
    if (move.current === "input") inputRef.current?.focus();
    if (move.current === "change") changeRef.current?.focus();
    move.current = null;
  }, [editing, name]);

  // Persistent live region so the announcement is read when the name appears.
  const live = <span role="status" className="sr-only">{saved && name ? `Working as ${name}` : ""}</span>;

  if (name && !editing) {
    return (
      <>
        {live}
      <div className="ml-auto flex shrink-0 items-center gap-2 text-sm">
        <UserRound aria-hidden className="size-4 text-muted-foreground" />
        <span className="font-medium">{name}</span>
        <Button ref={changeRef} variant="ghost" size="sm" onClick={() => { setDraft(name); setSaved(false); move.current = "input"; setEditing(true); }}>
          Change
        </Button>
      </div>
      </>
    );
  }
  return (
    <>
      {live}
    <form
      className="ml-auto flex shrink-0 items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setName(draft);
        setSaved(true);
        move.current = "change";
        setEditing(false);
      }}
    >
      <label htmlFor="who" className="sr-only">
        Your name
      </label>
      <Input ref={inputRef} id="who" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={40} placeholder="Your name to claim leads" className="h-9 w-52" />
      <Button type="submit" size="sm" disabled={!draft.trim()}>
        Save
      </Button>
    </form>
    </>
  );
}
