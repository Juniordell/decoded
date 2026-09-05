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
  title: "Institutions",
  description: "Labs and universities publishing in the papers Decoded tracks.",
};

export default async function InstitutionsPage() {
  const data = await api.getInstitutions(100);

  return (
    <PageShell>
      <Column>
        <div className="mb-[22px] flex flex-wrap items-baseline justify-between gap-4">
          <PageTitle>Institutions</PageTitle>
          <Link
            href="/authors"
            className="font-mono text-[12px] uppercase tracking-[0.14em] text-accent transition-opacity hover:opacity-70"
          >
            Authors →
          </Link>
        </div>

        <PageLead className="mb-[clamp(32px,4vw,44px)]">
          Labs and universities behind the papers in the corpus, ranked by
          output.
        </PageLead>

        <div className="border-t border-rule-strong">
          {(data.institutions ?? []).map((i) => (
            <div
              key={i.slug}
              className="row-shift group border-b border-border last:border-b-0"
            >
              <Link
                href={`/institution/${i.slug}`}
                className="flex items-baseline justify-between gap-5 py-4"
              >
                <p className="min-w-0 truncate text-[16.5px] transition-colors group-hover:text-accent">
                  {i.name}
                </p>
                <span className="tnum shrink-0 font-mono text-[12px] text-subtle">
                  {i.paper_count} papers · {i.author_count} authors
                </span>
              </Link>
            </div>
          ))}
        </div>
      </Column>

      <Rail>
        <RailHeading>Where it breaks</RailHeading>
        <RailNote>
          Affiliations come from what the paper itself declares. A researcher who
          moved between labs shows up under whichever one the paper listed at
          publication time.
        </RailNote>
      </Rail>
    </PageShell>
  );
}
