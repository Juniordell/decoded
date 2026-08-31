import type { Metadata } from "next";
import Link from "next/link";
import { api } from "@/lib/api";

export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Institutions",
  description: "Labs and universities publishing in the papers Decoded tracks.",
};

export default async function InstitutionsPage() {
  const data = await api.getInstitutions(100);

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="font-serif text-4xl leading-tight tracking-tight">
          Institutions
        </h1>
        <Link
          href="/authors"
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:underline"
        >
          Authors →
        </Link>
      </div>

      <div className="mt-10">
        {(data.institutions ?? []).map((i) => (
          <Link
            key={i.slug}
            href={`/institution/${i.slug}`}
            className="group flex items-baseline justify-between gap-4 border-b border-border py-4 last:border-b-0"
          >
            <p className="min-w-0 truncate text-[15px] transition-colors group-hover:text-accent">
              {i.name}
            </p>
            <span className="tnum shrink-0 font-mono text-[11px] text-muted-foreground">
              {i.paper_count} papers · {i.author_count} authors
            </span>
          </Link>
        ))}
      </div>
    </main>
  );
}
