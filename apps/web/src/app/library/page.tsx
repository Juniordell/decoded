"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { PaperCardSkeleton } from "@/components/paper-card";
import { useApi } from "@/lib/use-api";
import { relativeTime } from "@/lib/format";

interface SavedResponse {
  papers: Array<{
    arxiv_id: string;
    title: string;
    one_sentence: string | null;
    published_at: string;
    is_decoded: boolean;
  }>;
  total: number;
}

interface MeResponse {
  display_name: string | null;
  email: string | null;
  plan: string;
  credits_remaining: number;
  saved_count: number;
}

export default function LibraryPage() {
  const { authedFetch } = useApi();

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => authedFetch<MeResponse>("/v1/me"),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["library"],
    queryFn: () => authedFetch<SavedResponse>("/v1/me/saved"),
  });

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-serif text-4xl leading-tight tracking-tight">
        Library
      </h1>

      {me && (
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          <span>{me.plan} plan</span>
          <span className="tnum">{me.credits_remaining} credits</span>
          <span className="tnum">{me.saved_count} saved</span>
        </div>
      )}

      <div className="mt-10">
        {isLoading && (
          <>
            <PaperCardSkeleton />
            <PaperCardSkeleton />
          </>
        )}

        {data && data.papers.length === 0 && (
          <p className="py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
            Nothing saved yet
          </p>
        )}

        {data?.papers.map((p) => (
          <article
            key={p.arxiv_id}
            className="border-b border-border py-6 last:border-b-0"
          >
            <Link href={`/paper/${p.arxiv_id}`} className="group block">
              <div className="mb-2 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <span className="tnum">{relativeTime(p.published_at)}</span>
                {p.is_decoded && <span className="text-accent">decoded</span>}
              </div>
              <h2 className="font-serif text-xl leading-snug tracking-tight transition-colors group-hover:text-accent">
                {p.title}
              </h2>
              {p.one_sentence && (
                <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
                  {p.one_sentence}
                </p>
              )}
            </Link>
          </article>
        ))}
      </div>
    </main>
  );
}
