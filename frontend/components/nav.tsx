"use client";

import { HeartPulse, KanbanSquare, LayoutDashboard, MessageSquareText, Search, ShieldBan, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Dashboard", Icon: LayoutDashboard },
  { href: "/search", label: "Search", Icon: Search },
  { href: "/leads", label: "Leads", Icon: Users },
  { href: "/pipeline", label: "Pipeline", Icon: KanbanSquare },
  { href: "/templates", label: "Templates", Icon: MessageSquareText },
  { href: "/suppression", label: "Suppression", Icon: ShieldBan },
];

export function Nav() {
  const path = usePathname();
  return (
    <header className="sticky top-0 z-30 border-b bg-header backdrop-blur">
      <nav aria-label="Main" className="flex h-14 items-center gap-6 px-(--spacing-gutter)">
        <Link href="/" className="flex shrink-0 items-center gap-2 rounded-md font-semibold tracking-tight">
          <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
            <HeartPulse className="size-4" />
          </span>
          <span className="hidden sm:inline">ZCS LeadEngine</span>
          <span className="sr-only sm:hidden">ZCS LeadEngine home</span>
        </Link>
        <ul className="flex min-w-0 items-center gap-1 overflow-x-auto p-1">
          {ITEMS.map(({ href, label, Icon }) => {
            const current = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={current ? "page" : undefined}
                  className={`flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-1.5 text-sm transition-colors ${
                    current ? "bg-accent font-semibold text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  <Icon aria-hidden className="size-4" />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
