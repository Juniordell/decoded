import { Suspense } from "react";
import { SearchBox } from "@/components/search-box";
import { SearchResults } from "@/components/search-results";
import { api } from "@/lib/api";

export const metadata = {
  title: "Search",
  description: "Semantic search across decoded AI research papers.",
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="mb-8 font-serif text-4xl leading-tight tracking-tight">
        Search
      </h1>

      <Suspense fallback={<div className="h-12 border-b border-border" />}>
        <SearchBox autoFocus />
      </Suspense>

      {q && (
        <Suspense
          key={q}
          fallback={
            <p className="mt-10 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              Searching…
            </p>
          }
        >
          <Results query={q} />
        </Suspense>
      )}
    </main>
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
      <div className="mt-10 border border-destructive/40 bg-destructive/5 p-5">
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-destructive">
          Search failed
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {e instanceof Error ? e.message : "Unknown error"}
        </p>
      </div>
    );
  }
}
