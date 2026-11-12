import { Globe, Mail, Phone, User } from "lucide-react";
import { formatPhone, hostOf, safeHttpUrl } from "@/lib/format";
import { PANEL_CLASS } from "@/lib/ui";

type Props = { person: string; title: string | null; phone: string | null; fax: string | null; email: string | null; website: string | null };

// The facts you need to reach someone, in large dark text, each one a link you can click.
export function ContactStrip({ person, title, phone, fax, email, website }: Props) {
  const url = safeHttpUrl(website);
  return (
    <section aria-label="How to reach this lead" className={`${PANEL_CLASS} grid gap-x-8 gap-y-4 sm:grid-cols-2 xl:grid-cols-4`}>
      <Item Icon={User} label="Contact person">
        {person ? (
          <>
            <span className="text-lg font-semibold">{person}</span>
            {title && <span className="block text-sm text-muted-foreground">{title}</span>}
          </>
        ) : (
          <span className="text-base text-muted-foreground">No named contact</span>
        )}
      </Item>
      <Item Icon={Phone} label="Phone">
        {phone ? (
          <a href={`tel:${phone.replace(/\D/g, "")}`} className="text-lg font-semibold tabular-nums underline-offset-4 hover:underline">
            {formatPhone(phone)}
          </a>
        ) : (
          <span className="text-base text-muted-foreground">No phone</span>
        )}
        {fax && <span className="block text-sm text-muted-foreground tabular-nums">Fax {formatPhone(fax)}</span>}
      </Item>
      <Item Icon={Mail} label="Email">
        {email ? (
          <a href={`mailto:${email}`} className="text-lg font-semibold break-all underline-offset-4 hover:underline">
            {email}
          </a>
        ) : (
          <span className="text-base text-muted-foreground">No email found yet</span>
        )}
      </Item>
      <Item Icon={Globe} label="Website">
        {url && website ? (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-lg font-semibold break-all underline-offset-4 hover:underline">
            {hostOf(website)}
          </a>
        ) : (
          <span className="text-base text-muted-foreground">No website found yet</span>
        )}
      </Item>
    </section>
  );
}

function Item({ Icon, label, children }: { Icon: typeof Phone; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span aria-hidden className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <div className="mt-0.5">{children}</div>
      </div>
    </div>
  );
}
