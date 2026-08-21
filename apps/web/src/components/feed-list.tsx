"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, type FeedResponse } from "@/lib/api";
import { PaperCard, PaperCardSkeleton } from "./paper-card";

const PAGE_SIZE = 20;

export function FeedList({
  initialData,
  category,
  decodedOnly,
}: {
  initialData: FeedResponse;
  category?: string;
  decodedOnly: boolean;
}) {
  const sentinel = useRef<HTMLDivElement>(null);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isError } =
    useInfiniteQuery({
      queryKey: ["feed", category ?? "all", decodedOnly],
      initialPageParam: 0,
      queryFn: ({ pageParam }) =>
        api.getFeed({
          limit: PAGE_SIZE,
          offset: pageParam as number,
          category,
          decodedOnly,
        }),
      getNextPageParam: (last, all) =>
        last.has_more ? all.length * PAGE_SIZE : undefined,
      initialData: {
        pages: [initialData],
        pageParams: [0],
      },
    });

  // Observa o sentinel e busca a próxima página quando ele entra em tela
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasNextPage) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      { rootMargin: "400px" },
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const papers = data.pages.flatMap((p) => p.papers);

  if (papers.length === 0) {
    return (
      <p className="py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
        No papers match this filter
      </p>
    );
  }

  return (
    <>
      <div>
        {papers.map((p) => (
          <PaperCard key={p.arxiv_id} paper={p} />
        ))}
      </div>

      <div ref={sentinel} className="py-4">
        {isFetchingNextPage && (
          <>
            <PaperCardSkeleton />
            <PaperCardSkeleton />
          </>
        )}
        {isError && (
          <p className="py-8 text-center font-mono text-xs text-destructive">
            Failed to load more
          </p>
        )}
        {!hasNextPage && papers.length > PAGE_SIZE && (
          <p className="py-8 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground/60">
            End of feed
          </p>
        )}
      </div>
    </>
  );
}