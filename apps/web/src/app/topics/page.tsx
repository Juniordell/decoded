import type { Metadata } from "next";
import Link from "next/link";
import { TopicCard } from "@/components/topics/topic-card";
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
  title: "Topics",
  description: "Every research topic Decoded tracks, discovered by clustering.",
};

const SORTS = [
  { key: "size", label: "Size" },
  { key: "momentum", label: "Momentum" },
  { key: "name", label: "A-Z" },
] as const;

export default async function TopicsPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort = "size" } = await searchParams;

  const data = await api.getTopics({ sort, limit: 200 });

  return (
    <PageShell>
      <Column>
        <PageTitle className="mb-[22px]">Topics</PageTitle>
        <PageLead className="mb-[clamp(32px,4vw,44px)]">
          {data.total} topics, discovered by clustering paper embeddings rather
          than assigned by hand.
        </PageLead>

        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-7 gap-y-4 border-b border-rule-strong pb-3">
          <div className="flex flex-wrap gap-x-[22px] gap-y-2">
            {SORTS.map((s) => (
              <Link
                key={s.key}
                href={`/topics?sort=${s.key}`}
                className={`font-mono text-[12px] uppercase tracking-[0.14em] transition-colors ${
                  sort === s.key
                    ? "text-foreground"
                    : "text-subtle hover:text-foreground"
                }`}
              >
                {s.label}
              </Link>
            ))}
          </div>

          <Link
            href="/pulse"
            className="font-mono text-[12px] uppercase tracking-[0.14em] text-accent transition-opacity hover:opacity-70"
          >
            Field Pulse →
          </Link>
        </div>

        <div>
          {(data.topics ?? []).map((t) => (
            <TopicCard key={t.slug} topic={t} />
          ))}
        </div>
      </Column>

      <Rail>
        <RailHeading>How topics are found</RailHeading>
        <RailNote>
          Abstracts are embedded and clustered; each cluster is labelled from its
          own vocabulary. Nothing here comes from a taxonomy someone wrote once,
          which is why the names read like the papers rather than like a
          catalogue.
        </RailNote>
      </Rail>
    </PageShell>
  );
}
