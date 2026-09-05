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
    const a = await api.getAuthor(slug);
    return {
      title: a.name,
      description: `${a.paper_count} papers by ${a.name}${
        a.affiliation ? ` at ${a.affiliation}` : ""
      }, decoded for humans.`,
    };
  } catch {
    return { title: "Author not found", robots: { index: false } };
  }
}

function formatYear(iso: string | null | undefined): string {
  return iso ? new Date(iso).getFullYear().toString() : "—";
}

export default async function AuthorPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let author;
  try {
    author = await api.getAuthor(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const topics = author.topics ?? [];
  const coauthors = author.coauthors ?? [];
  const papers = author.papers ?? [];

  return (
    <PageShell tight>
      <Column>
        <BackLink href="/authors">← Authors</BackLink>

        <div className="mt-7 flex items-start justify-between gap-6">
          <div className="min-w-0">
            <PageTitle className="text-[clamp(32px,4.2vw,48px)]">
              {author.name}
            </PageTitle>
            {author.affiliation && (
              <p className="mt-3 text-[17px] text-muted-foreground">
                {author.institution_slug ? (
                  <Link
                    href={`/institution/${author.institution_slug}`}
                    className="transition-colors hover:text-accent"
                  >
                    {author.affiliation}
                  </Link>
                ) : (
                  author.affiliation
                )}
              </p>
            )}
          </div>
          <div className="shrink-0">
            <FollowButton
              targetType="author"
              slug={author.slug}
              initialFollowing={author.is_following}
            />
          </div>
        </div>

        <div className="mt-9 grid grid-cols-3 gap-6 border-y border-border py-6">
          <Stat label="Papers" value={author.paper_count} />
          <Stat label="Citations" value={author.total_citations} />
          <Stat
            label="Active"
            value={
              <>
                {formatYear(author.first_paper_at)}
                {formatYear(author.first_paper_at) !==
                  formatYear(author.latest_paper_at) &&
                  `–${formatYear(author.latest_paper_at)}`}
              </>
            }
          />
        </div>

        <div className="mt-12 space-y-12">
          {topics.length > 0 && (
            <SubSection label="Works on" className="border-t-0 pt-0">
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

          {coauthors.length > 0 && (
            <SubSection label="Frequent collaborators">
              <div className="space-y-2">
                {coauthors.map((c) => (
                  <div
                    key={c.slug}
                    className="flex items-baseline justify-between gap-5"
                  >
                    <Link
                      href={`/author/${c.slug}`}
                      className="truncate text-[16px] transition-colors hover:text-accent"
                    >
                      {c.name}
                    </Link>
                    <span className="tnum shrink-0 font-mono text-[12px] text-subtle">
                      {c.shared_papers} together
                    </span>
                  </div>
                ))}
              </div>
            </SubSection>
          )}

          <SubSection label="Papers">
            <div>
              {papers.map((p) => (
                <PaperCard key={p.arxiv_id} paper={p} source="author" />
              ))}
            </div>
          </SubSection>
        </div>
      </Column>

      <Rail>
        <RailHeading>How this page is built</RailHeading>
        <RailNote>
          Everything here comes from the papers themselves: affiliations as the
          paper declared them, collaborators as they appear on the byline.
        </RailNote>
        {!author.is_disambiguated && (
          <div className="mt-[22px] border-l-2 border-accent bg-tint px-5 py-4">
            <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
              Where it breaks
            </div>
            <p className="text-[15.5px] leading-[1.55] text-foreground/90 [text-wrap:pretty]">
              This page is grouped by name. Papers by different researchers who
              share this name may be mixed together.
            </p>
          </div>
        )}
      </Rail>
    </PageShell>
  );
}
