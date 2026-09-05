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
      <div className="border-b border-border pb-[46px] pt-[42px]">
        <p className="mb-3.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          Nothing decoded here yet
        </p>
        <p className="max-w-[46ch] font-serif text-[21px] leading-[1.45] [text-wrap:pretty]">
          No paper in this filter has cleared the queue. It runs in
          community-signal order — opening one moves it up.
        </p>
      </div>
    );
  }

  return (
    <>
      <div>
        {papers.map((p, i) => (
          <PaperCard key={p.arxiv_id} paper={p} source="feed" position={i} />
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
          <p className="py-8 font-mono text-[11.5px] uppercase tracking-[0.14em] text-destructive">
            Failed to load more
          </p>
        )}
        {!hasNextPage && papers.length > PAGE_SIZE && (
          <p className="flex items-center gap-4 py-8 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
            <span className="flex-none">End of feed</span>
            <span aria-hidden="true" className="h-px flex-1 bg-border" />
          </p>
        )}
      </div>
    </>
  );
}