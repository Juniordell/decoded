import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PaperCard } from "@/components/paper-card";
import { TimelineChart } from "@/components/topics/timeline-chart";
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
    <main className="mx-auto max-w-2xl px-6 py-12">
      <Link
        href="/topics"
        className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:text-accent"
      >
        ← Topics
      </Link>

      <div className="mt-5 flex items-start justify-between gap-6">
        <h1 className="min-w-0 font-serif text-[34px] leading-[1.15] tracking-tight">
          {topic.name}
        </h1>
        <div className="shrink-0">
          <FollowButton targetType="topic" slug={topic.slug} />
        </div>
      </div>

      {topic.description && (
        <p className="mt-4 text-[16px] leading-relaxed text-muted-foreground">
          {topic.description}
        </p>
      )}

      {keywords.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/60">
          {keywords.slice(0, 8).map((k) => (
            <span key={k}>{k}</span>
          ))}
        </div>
      )}

      {/* Números */}
      <div className="mt-8 grid grid-cols-3 gap-6 border-y border-border py-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Papers
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {topic.paper_count}
          </p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Last 4 weeks
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {topic.recent_papers}
          </p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            {MOMENTUM_COPY[topic.momentum_label] ?? "Trend"}
          </p>
          <p
            className={`tnum mt-1 font-serif text-2xl leading-none ${
              topic.momentum_label === "rising"
                ? "text-accent"
                : topic.momentum_label === "cooling"
                  ? "text-muted-foreground"
                  : ""
            }`}
          >
            {topic.momentum_label === "new"
              ? "—"
              : momentumPct > 0
                ? `+${momentumPct}%`
                : `${momentumPct}%`}
          </p>
        </div>
      </div>

      {/* Gráfico */}
      <section className="mt-10">
        <h2 className="mb-4 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Papers per week
        </h2>
        <TimelineChart points={timeline} />
      </section>

      {/* Autores */}
      {authors.length > 0 && (
        <section className="mt-12 border-t border-border pt-8">
          <h2 className="mb-4 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Most active authors
          </h2>
          <div className="space-y-2.5">
            {authors.map((a) => (
              <div
                key={a.name}
                className="grid gap-1 sm:grid-cols-[1fr_auto] sm:gap-4"
              >
                <div className="min-w-0">
                  <p className="truncate text-[14px]">{a.name}</p>
                  {a.affiliation && (
                    <p className="truncate text-[12px] text-muted-foreground">
                      {a.affiliation}
                    </p>
                  )}
                </div>
                <p className="tnum shrink-0 font-mono text-[11px] text-muted-foreground">
                  {a.paper_count} papers
                  {a.total_citations > 0 && ` · ${a.total_citations} cites`}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Papers */}
      <section className="mt-12 border-t border-border pt-8">
        <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Papers
        </h2>
        <div>
          {papers.map((p) => (
            <PaperCard key={p.arxiv_id} paper={p} />
          ))}
        </div>
      </section>
    </main>
  );
}
