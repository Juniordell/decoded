"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Show, SignInButton, UserButton } from "@clerk/nextjs";
import { DecodedLogo } from "@/components/brand";

const NAV = [
  { href: "/", label: "Feed" },
  { href: "/pulse", label: "Pulse" },
  { href: "/search", label: "Search" },
  { href: "/listen", label: "Listen" },
] as const;

export function SiteHeader() {
  const pathname = usePathname();

  // A página de um paper continua sendo o feed para efeito de navegação
  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/" || pathname.startsWith("/paper/");
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/[0.94] backdrop-blur-[6px]">
      <div className="mx-auto flex max-w-[1240px] items-center justify-between gap-8 px-6 py-3.5 sm:px-10">
        <div className="flex min-w-0 items-center gap-5">
          <Link href="/" aria-label="Decoded — home" className="flex-none leading-[0]">
            <DecodedLogo width={126} />
          </Link>
          <span className="hidden whitespace-nowrap font-mono text-[11px] uppercase tracking-[0.16em] text-subtle md:inline">
            AI research, explained
          </span>
        </div>

        <nav className="flex items-center gap-5 sm:gap-7">
          {NAV.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`border-b-2 pb-[3px] pt-1 font-mono text-[12px] uppercase tracking-[0.14em] transition-colors ${
                  active
                    ? "border-accent text-foreground"
                    : "border-transparent text-subtle hover:text-foreground"
                }`}
              >
                {item.label}
              </Link>
            );
          })}

          <Show when="signed-in">
            <Link
              href="/library"
              aria-current={isActive("/library") ? "page" : undefined}
              className={`border-b-2 pb-[3px] pt-1 font-mono text-[12px] uppercase tracking-[0.14em] transition-colors ${
                isActive("/library")
                  ? "border-accent text-foreground"
                  : "border-transparent text-subtle hover:text-foreground"
              }`}
            >
              Library
            </Link>
            <UserButton />
          </Show>

          <Show when="signed-out">
            <SignInButton mode="modal">
              <button
                type="button"
                className="border-b border-accent-light pb-[3px] pt-1 font-mono text-[12px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
              >
                Sign in
              </button>
            </SignInButton>
          </Show>
        </nav>
      </div>
    </header>
  );
}
