import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { FollowButton } from "@/components/follow-button";
import { PaperCard } from "@/components/paper-card";
import {
  BackLink,
  Column,
  PageShell,
  PageTitle,
  Rail,
  RailHeading,
  RailNote,
  Stat,
  SubSection,
  WhereItBreaks,
} from "@/components/page-shell";
import { ApiError, api } from "@/lib/api";

export const revalidate = 1800;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const i = await api.getInstitution(slug);
    return {
      title: i.name,
      description: `${i.paper_count} papers from ${i.name}, decoded for humans.`,
    };
  } catch {
    return { title: "Institution not found", robots: { index: false } };
  }
}

export default async function InstitutionPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let inst;
  try {
    inst = await api.getInstitution(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const authors = inst.top_authors ?? [];
  const topics = inst.topics ?? [];
  const papers = inst.papers ?? [];

  return (
    <PageShell tight>
      <Column>
        <BackLink href="/institutions">← Institutions</BackLink>

        <div className="mt-7 flex items-start justify-between gap-6">
          <PageTitle className="min-w-0 text-[clamp(32px,4.2vw,48px)]">
            {inst.name}
          </PageTitle>
          <div className="shrink-0">
            <FollowButton
              targetType="institution"
              slug={inst.slug}
              initialFollowing={inst.is_following}
            />
          </div>
        </div>

        <div className="mt-9 grid grid-cols-3 gap-6 border-y border-border py-6">
          <Stat label="Papers" value={inst.paper_count} />
          <Stat label="Authors" value={inst.author_count} />
          <Stat label="Citations" value={inst.total_citations} />
        </div>

        <div className="mt-12 space-y-12">
          {topics.length > 0 && (
            <SubSection label="Research areas" className="border-t-0 pt-0">
              <div className="flex flex-wrap gap-x-5 gap-y-2.5">
                {topics.map((t) => (
                  <Link
                    key={t.slug}
                    href={`/topic/${t.slug}`}
                    className="text-[16px] transition-colors hover:text-accent"
                  >
                    {t.name}
                    <span className="tnum ml-2 font-mono text-[11.5px] text-subtle">
                      {t.paper_count}
                    </span>
                  </Link>
                ))}
              </div>
            </SubSection>
          )}

          {authors.length > 0 && (
            <SubSection label="Researchers">
              <div className="space-y-2">
                {authors.map((a) => (
                  <div
                    key={a.slug}
                    className="flex items-baseline justify-between gap-5"
                  >
                    <Link
                      href={`/author/${a.slug}`}
                      className="truncate text-[16px] transition-colors hover:text-accent"
                    >
                      {a.name}
                    </Link>
                    <span className="tnum shrink-0 font-mono text-[12px] text-subtle">
                      {a.paper_count} papers
                    </span>
                  </div>
                ))}
              </div>
            </SubSection>
          )}

          <SubSection label="Recent papers">
            <div>
              {papers.map((p) => (
                <PaperCard key={p.arxiv_id} paper={p} source="institution" />
              ))}
            </div>
          </SubSection>
        </div>
      </Column>

      <Rail>
        <RailHeading>How this page is built</RailHeading>
        <RailNote>
          Papers are attributed from the affiliations printed on them, then
          grouped by normalised institution name.
        </RailNote>
        <WhereItBreaks className="mt-[22px]">
          A lab that publishes under several names — a university, a department,
          a spin-out — can show up as more than one institution here.
        </WhereItBreaks>
      </Rail>
    </PageShell>
  );
}
