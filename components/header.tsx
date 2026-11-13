"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { SiteMark } from "@/components/site-mark";
import { SITE_NAME } from "@/lib/site";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/methods", label: "Methods" },
  { href: "/preferences", label: "Preferences" },
  { href: "/districts", label: "Districts" },
  { href: "/apportionment", label: "Apportionment" },
  { href: "/liquid", label: "Liquid" },
  { href: "/expressive", label: "Expressive" },
];

/**
 * The header above every demo: white with faint washes of the site's
 * bright accents, a palette hairline along the bottom, and the demos as a
 * pill group with the current one in navy. The home page lists every demo itself, so it
 * has no header. It does not stick, because several demos pin their own
 * rails to the top of the viewport.
 */
export default function Header() {
  const pathname = usePathname();
  const navRef = React.useRef<HTMLElement>(null);

  // On narrow screens the pills scroll sideways; keep the current one in view.
  // Only the pill row is scrolled. scrollIntoView would also scroll the page
  // back up to the header whenever it is off screen, which threw the reader
  // to the top on every move between the pages of one demo.
  React.useEffect(() => {
    const nav = navRef.current;
    const current = nav?.querySelector('[aria-current="page"]');
    if (!nav || !current) return;
    const row = nav.getBoundingClientRect();
    const pill = current.getBoundingClientRect();
    const inset = 16; // the row's side padding
    if (pill.left < row.left + inset) nav.scrollLeft -= row.left + inset - pill.left;
    else if (pill.right > row.right - inset) nav.scrollLeft += pill.right - (row.right - inset);
  }, [pathname]);

  if (pathname === "/") return null;

  return (
    <header className="relative isolate overflow-hidden bg-white text-site-navy">
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-[radial-gradient(34%_160%_at_0%_0%,rgb(226_69_126/0.1),transparent_70%),radial-gradient(40%_180%_at_100%_100%,rgb(47_107_255/0.12),transparent_70%),radial-gradient(30%_160%_at_68%_0%,rgb(30_200_216/0.12),transparent_70%),radial-gradient(24%_160%_at_36%_100%,rgb(255_181_71/0.12),transparent_70%)]"
      />
      <div
        aria-hidden
        className="absolute inset-x-0 bottom-0 h-px bg-[linear-gradient(90deg,var(--color-site-aqua),var(--color-site-blue)_30%,var(--color-site-violet)_55%,var(--color-site-rose)_78%,var(--color-site-sun))]"
      />
      <div className="mx-auto flex max-w-[1600px] flex-col gap-2.5 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:px-6">
        <Link
          href="/"
          className="flex w-fit items-center gap-2.5 rounded-lg transition-opacity hover:opacity-85 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-site-blue"
        >
          <SiteMark />
          <span className="text-[15px] font-semibold tracking-tight">{SITE_NAME}</span>
        </Link>
        {/* On phones the pill row scrolls with no scrollbar; faded edges show
            that more demos sit off screen on either side. */}
        <nav ref={navRef} aria-label="Demos" className="-mx-4 scroll-px-4 overflow-x-auto px-4 [scrollbar-width:none] [mask-image:linear-gradient(90deg,transparent,#000_20px,#000_calc(100%-20px),transparent)] sm:mx-0 sm:px-0 sm:[mask-image:none]">
          <ul className="flex w-max items-center gap-0.5 rounded-full border border-site-navy/10 bg-white/80 p-1 shadow-[0_1px_2px_rgb(13_23_38/0.06)]">
            {navItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block rounded-full px-3 py-1 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-site-blue",
                      active
                        ? "bg-site-navy text-site-mist shadow-sm"
                        : "text-site-navy/70 hover:bg-site-blue/[0.08] hover:text-site-blue"
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
