"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/search", label: "Search" },
  { href: "/leads", label: "Leads" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/templates", label: "Templates" },
  { href: "/suppression", label: "Suppression" },
];

export function Nav() {
  const path = usePathname();
  return (
    <header className="border-b">
      <nav aria-label="Main" className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
        <span className="font-semibold">ZCS LeadEngine</span>
        {ITEMS.map((i) => {
          const current = i.href === "/" ? path === "/" : path.startsWith(i.href);
          return (
            <Link
              key={i.href}
              href={i.href}
              aria-current={current ? "page" : undefined}
              className={`rounded px-1 text-sm underline-offset-4 hover:underline ${
                current ? "font-semibold underline" : "text-muted-foreground"
              }`}
            >
              {i.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
