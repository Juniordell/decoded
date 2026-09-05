import { Suspense } from "react";
import Link from "next/link";
import { CategoryFilter } from "@/components/category-filter";
import { FeedList } from "@/components/feed-list";
import { PaperCardSkeleton } from "@/components/paper-card";
import {
  Column,
  ErrorNote,
  PageShell,
  Rail,
  RailBlock,
  RailHeading,
  RailNote,
} from "@/components/page-shell";
import { categoryLabel } from "@/lib/format";
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

  const countCaption = [
    decodedOnly ? "decoded papers" : "papers",
    category ? `in ${categoryLabel(category)}` : "across cs.AI, cs.CL, cs.LG and cs.CV",
  ].join(" ");

  return (
    <PageShell>
      <Column>
        <h1 className="mb-[22px] max-w-[20ch] font-serif text-[clamp(38px,4.8vw,58px)] font-semibold leading-[1.08] tracking-[-0.024em] [text-wrap:pretty]">
          Every AI paper, <span className="text-accent">explained for humans.</span>
        </h1>

        <p className="mb-[clamp(38px,4.5vw,56px)] max-w-[58ch] text-[19px] leading-[1.6] text-foreground/80 [text-wrap:pretty]">
          New research from arXiv, decoded into one sentence, a sixty-second
          read, figures explained, and analogies that name where they break. No
          PhD required.
        </p>

        <Suspense fallback={<div className="mb-2 h-9 border-b border-rule-strong" />}>
          <CategoryFilter />
        </Suspense>

        {error ? (
          <div className="mt-8">
            <ErrorNote title="API unreachable" message={error} />
          </div>
        ) : initialData ? (
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
        ) : null}
      </Column>

      {initialData && (
        <Rail>
          <RailHeading>The index</RailHeading>

          <RailBlock>
            <div className="tnum mb-2 font-serif text-[52px] font-bold leading-[0.9] tracking-[-0.04em]">
              {initialData.total.toLocaleString("en-US")}
            </div>
            <div className="font-mono text-[11.5px] leading-[1.5] tracking-[0.1em] text-muted-foreground">
              {countCaption}
            </div>
          </RailBlock>

          <RailBlock className="flex flex-col gap-2.5 font-mono text-[12px]">
            <Link
              href="/pulse"
              className="text-muted-foreground transition-colors hover:text-accent"
            >
              what&apos;s heating up →
            </Link>
            <Link
              href="/topics"
              className="text-muted-foreground transition-colors hover:text-accent"
            >
              every topic tracked →
            </Link>
            <Link
              href="/listen"
              className="text-muted-foreground transition-colors hover:text-accent"
            >
              papers as audio →
            </Link>
          </RailBlock>

          <RailNote>
            Papers are ranked by community signal — Hacker News mentions and
            citation velocity — then decoded in that order. Anything already
            decoded stays free at a permanent URL.
          </RailNote>
        </Rail>
      )}
    </PageShell>
  );
}
