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

  const item =
    "font-mono text-[12px] uppercase tracking-[0.14em] transition-colors";

  return (
    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-7 gap-y-4 border-b border-rule-strong pb-3">
      <div className="flex flex-wrap gap-x-[22px] gap-y-2">
        <Link
          href={buildHref({ category: null })}
          className={`${item} ${
            active === null
              ? "text-foreground"
              : "text-subtle hover:text-foreground"
          }`}
        >
          All
        </Link>

        {CATEGORIES.map((c) => (
          <Link
            key={c}
            href={buildHref({ category: c })}
            title={categoryLabel(c)}
            className={`${item} ${
              active === c
                ? "text-foreground"
                : "text-subtle hover:text-foreground"
            }`}
          >
            {c.replace("cs.", "")}
          </Link>
        ))}
      </div>

      <Link
        href={buildHref({ decoded: decodedOnly ? null : "1" })}
        className={`${item} ${
          decodedOnly ? "text-accent" : "text-subtle hover:text-foreground"
        }`}
      >
        Decoded only
      </Link>
    </div>
  );
}
