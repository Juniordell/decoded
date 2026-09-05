import { Suspense } from "react";
import { SearchBox } from "@/components/search-box";
import { SearchResults } from "@/components/search-results";
import {
  Column,
  ErrorNote,
  PageShell,
  PageTitle,
  Rail,
  RailBlock,
  RailHeading,
  RailNote,
} from "@/components/page-shell";
import { api } from "@/lib/api";

export const metadata = {
  title: "Search",
  description: "Semantic search across decoded AI research papers.",
  robots: { index: true, follow: true },
};

const SEARCHED = [
  "one-sentence layer",
  "60-second read",
  "deep dive sections",
  "figure explanations",
  "vocabulary entries",
];

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;

  return (
    <PageShell>
      <Column>
        <PageTitle className="mb-[clamp(36px,4.5vw,56px)]">Search</PageTitle>

        <Suspense
          fallback={<div className="h-12 border-b border-rule-strong" />}
        >
          <SearchBox autoFocus />
        </Suspense>

        {q && (
          <Suspense
            key={q}
            fallback={
              <p className="mt-10 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
                Searching…
              </p>
            }
          >
            <Results query={q} />
          </Suspense>
        )}
      </Column>

      <Rail>
        <RailHeading>What is searched</RailHeading>
        <RailBlock className="flex flex-col gap-2.5 font-mono text-[12px] text-muted-foreground">
          {SEARCHED.map((item) => (
            <span key={item}>{item}</span>
          ))}
          <span className="text-subtle">not the raw PDF</span>
        </RailBlock>
        <RailNote>
          Results quote the passage they matched, so you can judge the hit before
          you open it.
        </RailNote>
      </Rail>
    </PageShell>
  );
}

async function Results({ query }: { query: string }) {
  try {
    const res = await api.search({ q: query, limit: 10 });

    return (
      <SearchResults
        hits={res.hits ?? []}
        reranked={res.reranked}
        latencyMs={res.latency_ms}
        totalFound={res.total_found}
      />
    );
  } catch (e) {
    return (
      <div className="mt-10">
        <ErrorNote
          title="Search failed"
          message={e instanceof Error ? e.message : "Unknown error"}
        />
      </div>
    );
  }
}
