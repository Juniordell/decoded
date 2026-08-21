"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { categoryLabel } from "@/lib/format";

const CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"] as const;

export function CategoryFilter() {
  const pathname = usePathname();
  const params = useSearchParams();
  const active = params.get("category");
  const decodedOnly = params.get("decoded") === "1";

  function buildHref(patch: Record<string, string | null>): string {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    const qs = next.toString();
    return qs ? `${pathname}?${qs}` : pathname;
  }

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-border pb-4 font-mono text-[11px] uppercase tracking-[0.14em]">
      <Link
        href={buildHref({ category: null })}
        className={
          active === null
            ? "text-foreground"
            : "text-muted-foreground transition-colors hover:text-foreground"
        }
      >
        All
      </Link>

      {CATEGORIES.map((c) => (
        <Link
          key={c}
          href={buildHref({ category: c })}
          title={categoryLabel(c)}
          className={
            active === c
              ? "text-foreground"
              : "text-muted-foreground transition-colors hover:text-foreground"
          }
        >
          {c.replace("cs.", "")}
        </Link>
      ))}

      <span className="ml-auto">
        <Link
          href={buildHref({ decoded: decodedOnly ? null : "1" })}
          className={
            decodedOnly
              ? "text-accent"
              : "text-muted-foreground transition-colors hover:text-foreground"
          }
        >
          {decodedOnly ? "✓ decoded only" : "decoded only"}
        </Link>
      </span>
    </div>
  );
}