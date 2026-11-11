import type { Lead } from "@/lib/api";
import { SCORE_FACTORS } from "@/lib/constants";
import { formatPhone } from "@/lib/format";

type Factor = { points: number; max: number; reason: string };

function address(l: Lead["locations"][number]) {
  const street = [l.address_1, l.address_2].filter(Boolean).join(", ");
  const place = [l.city, [l.state, l.zip].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  return [street, place].filter(Boolean).join(", ") || "No address";
}

export function LeadRowDetail({ lead }: { lead: Lead }) {
  const comps = (lead.score?.components ?? {}) as Record<string, Factor>;
  return (
    <div className="grid gap-6 p-4 md:grid-cols-3">
      <section aria-label={`Score breakdown for ${lead.name}`}>
        <h3 className="mb-2 text-sm font-semibold">Score breakdown</h3>
        {lead.score ? (
          <>
            <ul className="space-y-1 text-sm">
              {SCORE_FACTORS.map(({ key, label }) => {
                const f = comps[key];
                return (
                  <li key={key}>
                    {f ? (
                      <>
                        <span className="font-medium">{label}:</span> {f.points} of {f.max}
                        <span className="text-muted-foreground">, {f.reason}</span>
                      </>
                    ) : (
                      <>
                        <span className="font-medium">{label}:</span> <span className="text-muted-foreground">not scored</span>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className="mt-2 text-sm">
              <span className="font-medium">Total:</span> {lead.fit_score ?? "-"} of 100
              <span className="text-muted-foreground"> (config {lead.score.config_version})</span>
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Not scored yet.</p>
        )}
      </section>
      <section aria-label={`Locations for ${lead.name}`}>
        <h3 className="mb-2 text-sm font-semibold">Locations ({lead.locations.length})</h3>
        {lead.locations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No locations on record.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {lead.locations.map((l, i) => (
              <li key={i}>
                <span className="font-medium">{l.purpose ?? "Location"}</span>
                {l.is_primary && <span className="text-muted-foreground"> (primary)</span>}
                <br />
                {address(l)}
                {l.phone && <span className="text-muted-foreground">, {formatPhone(l.phone)}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label={`Source for ${lead.name}`}>
        <h3 className="mb-2 text-sm font-semibold">Source</h3>
        {lead.source ? (
          <p className="text-sm">
            {lead.source.source_key}
            <br />
            <span className="text-muted-foreground">Collected {new Date(lead.source.collected_at).toLocaleDateString()}</span>
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No source recorded.</p>
        )}
        <p className="mt-2 text-sm text-muted-foreground">NPI {lead.npi}</p>
      </section>
    </div>
  );
}
