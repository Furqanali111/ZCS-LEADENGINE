"use client";

import Link from "next/link";
import { Check, Copy, Globe, Mail, Phone, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatPhone, hostOf, safeHttpUrl } from "@/lib/format";
import { PANEL_CLASS } from "@/lib/ui";
import { useCopy } from "@/lib/use-copy";

type Props = { person: string; title: string | null; phone: string | null; fax: string | null; email: string | null; website: string | null };

// The facts you need to reach someone, large and dark. Each value selects whole on a click and has a Copy button.
export function ContactStrip({ person, title, phone, fax, email, website }: Props) {
  const url = safeHttpUrl(website);
  const { copied, failed, copy } = useCopy();

  const copyButton = (label: string, text: string) => (
    <Button type="button" variant="outline" size="sm" className="shrink-0" aria-label={`Copy ${label.toLowerCase()}`} onClick={() => copy(label, text)}>
      {copied === label ? <Check aria-hidden className="text-emerald-700" /> : <Copy aria-hidden />}
      {copied === label ? "Copied" : failed === label ? "Copy failed, select the text" : "Copy"}
    </Button>
  );

  const phoneText = phone ? formatPhone(phone) : null;
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
      <Item Icon={Phone} label="Phone">
        {phoneText && phone ? (
          <>
            <Row>
              <span className="text-2xl font-semibold tabular-nums select-all">{phoneText}</span>
              {copyButton("Phone", phoneText)}
            </Row>
            <a href={`tel:${phone.replace(/\D/g, "")}`} className="mt-1 inline-block text-sm underline underline-offset-4">
              Call from this device
            </a>
          </>
        ) : (
          <span className="text-lg text-muted-foreground">No phone</span>
        )}
        {fax && <span className="mt-1 block text-sm text-muted-foreground tabular-nums">Fax {formatPhone(fax)}</span>}
      </Item>
      <Item Icon={Mail} label="Email">
        {email ? (
          <>
            <Row>
              <span className="text-2xl font-semibold break-all select-all">{email}</span>
              {copyButton("Email", email)}
            </Row>
            <a href={`mailto:${email}`} className="mt-1 inline-block text-sm underline underline-offset-4">
              Open in mail app
            </a>
          </>
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
