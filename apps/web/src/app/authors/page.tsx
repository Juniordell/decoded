import type { Metadata } from "next";
import Link from "next/link";
import { api } from "@/lib/api";

export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Authors",
  description: "Researchers publishing across the papers Decoded tracks.",
};

export default async function AuthorsPage() {
  const data = await api.getAuthors(100);

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="font-serif text-4xl leading-tight tracking-tight">
          Authors
        </h1>
        <Link
          href="/institutions"
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:underline"
        >
          Institutions →
        </Link>
      </div>

      <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
        Researchers with more than one paper in the corpus, ranked by output.
      </p>

      <div className="mt-10">
        {(data.authors ?? []).map((a) => (
          <Link
            key={a.slug}
            href={`/author/${a.slug}`}
            className="group flex items-baseline justify-between gap-4 border-b border-border py-4 last:border-b-0"
          >
            <div className="min-w-0">
              <p className="truncate text-[15px] transition-colors group-hover:text-accent">
                {a.name}
                {!a.is_disambiguated && (
                  <span className="ml-2 font-mono text-[9px] uppercase tracking-wider text-muted-foreground/50">
                    name match
                  </span>
                )}
              </p>
              {a.affiliation && (
                <p className="truncate text-[12px] text-muted-foreground">
                  {a.affiliation}
                </p>
              )}
            </div>
            <span className="tnum shrink-0 font-mono text-[11px] text-muted-foreground">
              {a.paper_count} papers
            </span>
          </Link>
        ))}
      </div>
    </main>
  );
}