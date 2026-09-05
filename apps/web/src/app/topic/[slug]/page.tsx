import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PaperCard } from "@/components/paper-card";
import { TimelineChart } from "@/components/topics/timeline-chart";
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
import { FollowButton } from "@/components/follow-button";

export const revalidate = 1800;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const topic = await api.getTopic(slug);
    return {
      title: topic.name,
      description:
        topic.description ??
        `${topic.paper_count} papers on ${topic.name}, decoded for humans.`,
    };
  } catch {
    return { title: "Topic not found", robots: { index: false } };
  }
}

const MOMENTUM_COPY: Record<string, string> = {
  rising: "Heating up",
  cooling: "Cooling down",
  steady: "Steady",
  new: "New topic",
  quiet: "Quiet",
};

export default async function TopicPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let topic;
  try {
    topic = await api.getTopic(slug, 12);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const keywords = topic.keywords ?? [];
  const timeline = topic.timeline ?? [];
  const authors = topic.top_authors ?? [];
  const papers = topic.papers ?? [];

  const momentumPct = Math.round(topic.momentum * 100);

  return (
    <PageShell tight>
      <Column>
        <BackLink href="/topics">← Topics</BackLink>

        <div className="mt-7 flex items-start justify-between gap-6">
          <PageTitle className="min-w-0 text-[clamp(32px,4.2vw,48px)]">
            {topic.name}
          </PageTitle>
          <div className="shrink-0">
            <FollowButton targetType="topic" slug={topic.slug} />
          </div>
        </div>

        {topic.description && (
          <p className="mt-5 max-w-[58ch] text-[18px] leading-[1.6] text-muted-foreground [text-wrap:pretty]">
            {topic.description}
          </p>
        )}

        {keywords.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-subtle">
            {keywords.slice(0, 8).map((k) => (
              <span key={k}>{k}</span>
            ))}
          </div>
        )}

        <div className="mt-9 grid grid-cols-3 gap-6 border-y border-border py-6">
          <Stat label="Papers" value={topic.paper_count} />
          <Stat label="Last 4 weeks" value={topic.recent_papers} />
          <Stat
            label={MOMENTUM_COPY[topic.momentum_label] ?? "Trend"}
            tone={
              topic.momentum_label === "rising"
                ? "accent"
                : topic.momentum_label === "cooling"
                  ? "muted"
                  : "default"
            }
            value={
              topic.momentum_label === "new"
                ? "—"
                : momentumPct > 0
                  ? `+${momentumPct}%`
                  : `−${Math.abs(momentumPct)}%`
            }
          />
        </div>

        <div className="mt-12 space-y-12">
          <SubSection label="Papers per week" className="border-t-0 pt-0">
            <TimelineChart points={timeline} />
          </SubSection>

          {authors.length > 0 && (
            <SubSection label="Most active authors">
              <div className="space-y-3">
                {authors.map((a) => (
                  <div
                    key={a.name}
                    className="grid gap-1 sm:grid-cols-[1fr_auto] sm:gap-5"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[16px]">{a.name}</p>
                      {a.affiliation && (
                        <p className="truncate font-mono text-[11.5px] text-subtle">
                          {a.affiliation}
                        </p>
                      )}
                    </div>
                    <p className="tnum shrink-0 font-mono text-[12px] text-subtle">
                      {a.paper_count} papers
                      {a.total_citations > 0 && ` · ${a.total_citations} cites`}
                    </p>
                  </div>
                ))}
              </div>
            </SubSection>
          )}

          <SubSection label="Papers">
            <div>
              {papers.map((p) => (
                <PaperCard key={p.arxiv_id} paper={p} source="topic" />
              ))}
            </div>
          </SubSection>
        </div>
      </Column>

      <Rail>
        <RailHeading>How this topic was found</RailHeading>
        <RailNote>
          Abstracts are embedded and clustered; the name comes from the
          cluster&apos;s own vocabulary, not from a taxonomy.
        </RailNote>
        <WhereItBreaks className="mt-[22px]">
          A paper sits in one cluster even when it belongs in two. Work that
          straddles subfields will be under-counted here.
        </WhereItBreaks>
      </Rail>
    </PageShell>
  );
}
