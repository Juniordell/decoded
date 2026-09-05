import type { Metadata } from "next";
import Link from "next/link";
import { TopicCard } from "@/components/topics/topic-card";
import {
  Column,
  ErrorNote,
  PageLead,
  PageShell,
  PageTitle,
  Rail,
  RailHeading,
  RailNote,
  WhereItBreaks,
} from "@/components/page-shell";
import { api } from "@/lib/api";

export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Field Pulse",
  description:
    "What's heating up and cooling down in AI research. Topics discovered automatically from arXiv, tracked week over week.",
};

function Group({
  label,
  hint,
  topics,
}: {
  label: string;
  hint: string;
  topics: React.ComponentProps<typeof TopicCard>["topic"][];
}) {
  if (topics.length === 0) return null;

  return (
    <section>
      <div className="mb-3.5">
        <h2 className="mb-1.5 font-mono text-[11.5px] uppercase tracking-[0.16em] text-accent">
          {label}
        </h2>
        <p className="text-[16.5px] leading-[1.5] text-muted-foreground">
          {hint}
        </p>
      </div>
      <div className="border-t border-border">
        {topics.map((t) => (
          <TopicCard key={t.slug} topic={t} showKeywords={false} />
        ))}
      </div>
    </section>
  );
}

export default async function PulsePage() {
  let pulse;
  let error: string | null = null;

  try {
    pulse = await api.getPulse();
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  return (
    <PageShell>
      <Column>
        <PageTitle className="mb-[22px]">Field Pulse</PageTitle>
        <PageLead>
          Topics discovered from what researchers are actually publishing — not
          from a taxonomy someone wrote once. Recounted every week.
        </PageLead>

        {error && (
          <div className="mt-8">
            <ErrorNote title="Pulse unavailable" message={error} />
          </div>
        )}

        {pulse && (
          <>
            <div className="tnum mb-[clamp(40px,5vw,64px)] mt-8 flex flex-wrap gap-x-8 gap-y-3 border-t border-rule-strong pt-3.5 font-mono text-[12px] uppercase tracking-[0.08em] text-muted-foreground">
              <span>{pulse.total_topics} topics</span>
              <span>{pulse.total_papers} papers</span>
              <span>{pulse.weeks_covered} weeks tracked</span>
            </div>

            <div className="space-y-[clamp(40px,5vw,64px)]">
              <Group
                label="Heating up"
                hint="More papers in the last four weeks than the four before."
                topics={pulse.rising ?? []}
              />
              <Group
                label="Emerging"
                hint="New topics with no prior week to compare against."
                topics={pulse.emerging ?? []}
              />
              <Group
                label="Cooling"
                hint="Fewer papers than the previous period."
                topics={pulse.cooling ?? []}
              />
              <Group
                label="Largest"
                hint="Most papers overall, regardless of trend."
                topics={pulse.largest ?? []}
              />
            </div>

            <div className="mt-[clamp(40px,5vw,64px)]">
              <Link
                href="/topics"
                className="border-b border-accent-light pb-0.5 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
              >
                All {pulse.total_topics} topics →
              </Link>
            </div>
          </>
        )}
      </Column>

      <Rail>
        <RailHeading>How topics are found</RailHeading>
        <RailNote>
          Abstracts are embedded, clustered, and labelled from the cluster&apos;s
          own vocabulary. Clusters that fall below a handful of papers in a week
          are dissolved.
        </RailNote>
        {pulse && (
          <WhereItBreaks className="mt-[22px]">
            {pulse.weeks_covered} weeks is a short baseline. A topic marked
            emerging may only be emerging inside our window.
          </WhereItBreaks>
        )}
      </Rail>
    </PageShell>
  );
}
