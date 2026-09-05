import type { Metadata } from "next";
import Link from "next/link";
import {
  Column,
  PageLead,
  PageShell,
  PageTitle,
  Rail,
  RailHeading,
  RailNote,
} from "@/components/page-shell";
import { api } from "@/lib/api";

export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Authors",
  description: "Researchers publishing across the papers Decoded tracks.",
};

export default async function AuthorsPage() {
  const data = await api.getAuthors(100);

  return (
    <PageShell>
      <Column>
        <div className="mb-[22px] flex flex-wrap items-baseline justify-between gap-4">
          <PageTitle>Authors</PageTitle>
          <Link
            href="/institutions"
            className="font-mono text-[12px] uppercase tracking-[0.14em] text-accent transition-opacity hover:opacity-70"
          >
            Institutions →
          </Link>
        </div>

        <PageLead className="mb-[clamp(32px,4vw,44px)]">
          Researchers with more than one paper in the corpus, ranked by output.
        </PageLead>

        <div className="border-t border-rule-strong">
          {(data.authors ?? []).map((a) => (
            <div
              key={a.slug}
              className="row-shift group border-b border-border last:border-b-0"
            >
              <Link
                href={`/author/${a.slug}`}
                className="flex items-baseline justify-between gap-5 py-4"
              >
                <div className="min-w-0">
                  <p className="truncate text-[16.5px] transition-colors group-hover:text-accent">
                    {a.name}
                    {!a.is_disambiguated && (
                      <span className="ml-2.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-subtle">
                        name match
                      </span>
                    )}
                  </p>
                  {a.affiliation && (
                    <p className="truncate font-mono text-[11.5px] text-subtle">
                      {a.affiliation}
                    </p>
                  )}
                </div>
                <span className="tnum shrink-0 font-mono text-[12px] text-subtle">
                  {a.paper_count} papers
                </span>
              </Link>
            </div>
          ))}
        </div>
      </Column>

      <Rail>
        <RailHeading>Where it breaks</RailHeading>
        <RailNote>
          Authors are grouped by name unless the corpus gives us something better
          to go on. Two researchers who share a name may share a page — those
          rows are marked &ldquo;name match&rdquo;.
        </RailNote>
      </Rail>
    </PageShell>
  );
}
