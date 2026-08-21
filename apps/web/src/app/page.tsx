import { Suspense } from "react";
import { CategoryFilter } from "@/components/category-filter";
import { FeedList } from "@/components/feed-list";
import { PaperCardSkeleton } from "@/components/paper-card";
import { api } from "@/lib/api";

export const revalidate = 300; // ISR: revalida a cada 5 min

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ category?: string; decoded?: string }>;
}) {
  const params = await searchParams;
  const category = params.category;
  const decodedOnly = params.decoded === "1";

  let initialData;
  let error: string | null = null;

  try {
    initialData = await api.getFeed({ limit: 20, category, decodedOnly });
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <div className="mb-10">
        <h1 className="font-serif text-4xl leading-tight tracking-tight sm:text-5xl">
          Every AI paper,
          <br />
          <span className="text-accent">explained for humans.</span>
        </h1>
        <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
          New research from arXiv, decoded into TL;DRs, deep dives, figure
          explanations, and analogies. No PhD required.
        </p>
      </div>

      <Suspense
        fallback={
          <div className="h-8 border-b border-border" />
        }
      >
        <CategoryFilter />
      </Suspense>

      {error ? (
        <div className="mt-8 border border-destructive/40 bg-destructive/5 p-5">
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-destructive">
            API unreachable
          </p>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
        </div>
      ) : initialData ? (
        <div className="mt-2">
          <Suspense
            fallback={
              <>
                <PaperCardSkeleton />
                <PaperCardSkeleton />
                <PaperCardSkeleton />
              </>
            }
          >
            <FeedList
              initialData={initialData}
              category={category}
              decodedOnly={decodedOnly}
            />
          </Suspense>
        </div>
      ) : null}
    </main>
  );
}