"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, Clock, Copy, Globe, Mail, MapPin, Phone, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatPhone, hostOf, safeHttpUrl } from "@/lib/format";
import { IS_DESKTOP, type Lead } from "@/lib/api";
import { PANEL_CLASS } from "@/lib/ui";
import { useCopy } from "@/lib/use-copy";

export type ShownPhone = { phone: string; source: string; differs: boolean; listingAddress?: string | null; collected: string | null };
type Props = {
  person: string;
  title: string | null;
  phones: ShownPhone[];
  fax: string | null;
  emails: { address: string; manual: boolean }[];
  onAddEmail: (email: string) => Promise<void>;
  website: string | null;
  hours: Lead["hours"];
  mapsUrl: string | null;
  isHospital: boolean;
  mapsStatus: string;
  lookingUp: boolean;
  lookupError: string | null;
  onLookup: () => void;
};

const SOURCE_LABELS: Record<string, string> = {
  npi_registry: "NPI Registry",
  npi_official: "NPI authorized official",
  google_maps: "Google Maps",
  practice_website: "Practice website",
};
export const sourceLabel = (key: string) => SOURCE_LABELS[key] ?? key.replace(/_/g, " ");
const MAPS_NOTE: Record<string, string> = {
  not_run: "Not looked up on Google Maps yet.",
  matched: "Matched on Google Maps.",
  no_match: "No Google Maps listing matched this address. Open the map to check by hand.",
  failed: "The last Google Maps lookup failed.",
};

// The facts you need to reach someone, large and dark. Each value selects whole on a click and has a Copy button.
export function ContactStrip({ person, title, phones, fax, emails, onAddEmail, website, hours, mapsUrl, isHospital, mapsStatus, lookingUp, lookupError, onLookup }: Props) {
  const url = safeHttpUrl(website);
  const { copied, failed, copy } = useCopy();
  const [newEmail, setNewEmail] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  async function addEmail(e: React.FormEvent) {
    e.preventDefault();
    if (!newEmail.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      await onAddEmail(newEmail.trim());
      setNewEmail("");
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Could not add the email");
    } finally {
      setAdding(false);
    }
  }

  const copyButton = (label: string, text: string) => (
    <>
    <Button type="button" variant="outline" size="sm" className="shrink-0" aria-label={`Copy ${label.toLowerCase()}`} onClick={() => copy(label, text)}>
      {copied === label ? <Check aria-hidden className="text-emerald-700" /> : <Copy aria-hidden />}
      {copied === label ? "Copied" : "Copy"}
    </Button>
    {failed === label && <span aria-hidden className="text-xs text-destructive">Copy failed</span>}
    </>
  );

  const mapsHref = safeHttpUrl(mapsUrl);
  const today = new Date().toLocaleDateString("en-US", { weekday: "long" });
  const todayHours = hours?.weekly.find((d) => d.day === today)?.hours;
  return (
    <section aria-label="How to reach this lead" className={`${PANEL_CLASS} grid gap-x-10 gap-y-6 p-6 md:grid-cols-2 min-[1900px]:grid-cols-4`}>
      <Item Icon={User} label="Contact person">
        {person ? (
          <>
            <span className="text-2xl font-semibold select-all">{person}</span>
            {title && <span className="block text-base text-muted-foreground">{title}</span>}
          </>
        ) : (
          <span className="text-lg text-muted-foreground">No named contact</span>
        )}
      </Item>
      <Item Icon={Phone} label={phones.length > 1 ? "Phones" : "Phone"}>
        {phones.length ? (
          <ul className="space-y-3">
            {phones.map((p) => {
              const text = formatPhone(p.phone);
              return (
                <li key={`${p.source}-${p.phone}`}>
                  <Row>
                    <span className="text-2xl font-semibold tabular-nums select-all">{text}</span>
                    {copyButton(`Phone ${sourceLabel(p.source)}`, text)}
                  </Row>
                  <span className="mt-0.5 block text-sm text-muted-foreground">
                    Source: {sourceLabel(p.source)}
                    {p.collected && `, ${p.collected.slice(0, 10)}`}
                    {p.differs && <span className="font-medium text-amber-700"> (differs from the NPI phone)</span>}
                    {p.listingAddress && <span className="block font-medium text-amber-700">Listing is at another address: {p.listingAddress}. The practice may have moved.</span>}
                  </span>
                  <a href={`tel:${p.phone.replace(/\D/g, "")}`} className="mt-0.5 inline-block text-sm underline underline-offset-4">
                    Call from this device
                  </a>
                </li>
              );
            })}
          </ul>
        ) : (
          <span className="text-lg text-muted-foreground">No phone</span>
        )}
        {fax && <span className="mt-1 block text-sm text-muted-foreground tabular-nums">Fax {formatPhone(fax)}</span>}
      </Item>
      <Item Icon={Mail} label={emails.length > 1 ? "Emails" : "Email"}>
        {emails.length ? (
          <ul className="space-y-3">
            {emails.map((m) => (
              <li key={m.address}>
                <Row>
                  <span className="text-2xl font-semibold break-all select-all">{m.address}</span>
                  {copyButton(`Email ${m.address}`, m.address)}
                </Row>
                <a href={`mailto:${m.address}`} className="mt-0.5 inline-block text-sm underline underline-offset-4">
                  Open in mail app
                </a>
                {m.manual && <span className="ml-3 text-sm text-muted-foreground">Added by hand</span>}
              </li>
            ))}
          </ul>
        ) : (
          <>
            <span className="text-lg text-muted-foreground">No email found yet</span>
            <span className="mt-1 block text-sm text-muted-foreground">
              Run a search with &quot;Also find websites and emails&quot; on.{" "}
              <Link href="/search" className="underline underline-offset-4">
                Go to search
              </Link>
            </span>
          </>
        )}
        <form onSubmit={addEmail} className="mt-3 flex flex-wrap items-center gap-2">
          <label htmlFor="add-email" className="sr-only">
            Add an email
          </label>
          <Input id="add-email" type="email" inputMode="email" placeholder="Add an email they gave you" className="w-64" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
          <Button type="submit" variant="outline" size="sm" disabled={adding || !newEmail.trim()}>
            {adding ? "Adding..." : "Add email"}
          </Button>
        </form>
        {addError && <span role="alert" className="mt-1 block text-sm text-destructive">{addError}</span>}
      </Item>
      <Item Icon={Globe} label="Website">
        {url && website ? (
          <>
            <Row>
              <span className="text-2xl font-semibold break-all select-all">{hostOf(website)}</span>
              {copyButton("Website", url)}
            </Row>
            <a href={url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-sm underline underline-offset-4">
              Open website
            </a>
          </>
        ) : (
          <>
            <span className="text-lg text-muted-foreground">No website found yet</span>
            <span className="mt-1 block text-sm text-muted-foreground">
              Run a search with &quot;Also find websites and emails&quot; on.{" "}
              <Link href="/search" className="underline underline-offset-4">
                Go to search
              </Link>
            </span>
          </>
        )}
      </Item>
      {(isHospital || mapsHref) && (
        <Item Icon={MapPin} label="Map and hours">
          {mapsHref && (
            <>
              <Row>
                <a href={mapsHref} target="_blank" rel="noopener noreferrer" className="text-lg font-semibold underline underline-offset-4">
                  Open in Google Maps
                </a>
                {copyButton("Map link", mapsHref)}
              </Row>
              <span className="mt-1 block text-sm text-muted-foreground">Check the number there and copy it if anything looks wrong.</span>
            </>
          )}
          {hours ? (
            <div className="mt-3">
              <p className="flex items-center gap-1.5 text-base font-semibold">
                <Clock aria-hidden className="size-4" />
                {todayHours ? `Today: ${todayHours}` : "Hours"}
              </p>
              <details className="mt-1 text-sm">
                <summary className="cursor-pointer underline underline-offset-4">Full week</summary>
                <ul className="mt-1 space-y-0.5 tabular-nums">
                  {hours.weekly.map((d) => (
                    <li key={d.day}>
                      {d.day}: {d.hours}
                    </li>
                  ))}
                </ul>
              </details>
              <span className="mt-1 block text-xs text-muted-foreground">Source: Google Maps, {hours.collected_at.slice(0, 10)}. Hospital local time.</span>
            </div>
          ) : (
            isHospital && <span className="mt-3 block text-sm text-muted-foreground">No hours found yet.</span>
          )}
          {/* The desktop bundle ships no browser for the lookup yet (docs/deferred-items.md), so the button would always fail there. */}
          {isHospital && !IS_DESKTOP && (
            <div className="mt-3">
              <Button type="button" variant="outline" size="sm" disabled={lookingUp} onClick={onLookup}>
                {lookingUp ? "Looking up, about 15 seconds..." : mapsStatus === "not_run" ? "Look up on Google Maps" : "Look up again"}
              </Button>
              <span className="mt-1 block text-sm text-muted-foreground">{lookupError ?? MAPS_NOTE[mapsStatus] ?? ""}</span>
            </div>
          )}
        </Item>
      )}
      <p role="status" className="sr-only">
        {copied ? `${copied} copied` : failed ? `Copy failed, select the ${failed.toLowerCase()}` : ""}
      </p>
    </section>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-x-3 gap-y-2">{children}</div>;
}

function Item({ Icon, label, children }: { Icon: typeof Phone; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4">
      <span aria-hidden className="mt-1 grid size-11 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
        <Icon className="size-5" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
        <div className="mt-1">{children}</div>
      </div>
    </div>
  );
}
