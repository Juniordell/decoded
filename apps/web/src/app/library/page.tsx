"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { PaperCardSkeleton } from "@/components/paper-card";
import {
  Column,
  PageShell,
  PageTitle,
  Rail,
  RailHeading,
  RailNote,
} from "@/components/page-shell";
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
    <PageShell>
      <Column>
        <PageTitle className="mb-[22px]">Library</PageTitle>

        {me && (
          <div className="mb-[clamp(32px,4vw,44px)] flex flex-wrap gap-x-7 gap-y-2 border-b border-rule-strong pb-3.5 font-mono text-[12px] uppercase tracking-[0.1em] text-muted-foreground">
            <span>{me.plan} plan</span>
            <span className="tnum">{me.credits_remaining} credits</span>
            <span className="tnum">{me.saved_count} saved</span>
          </div>
        )}

        <div>
          {isLoading && (
            <>
              <PaperCardSkeleton />
              <PaperCardSkeleton />
            </>
          )}

          {data && data.papers.length === 0 && (
            <div className="border-b border-border pb-[46px] pt-[42px]">
              <p className="mb-3.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
                Nothing saved yet
              </p>
              <p className="max-w-[46ch] font-serif text-[21px] leading-[1.45] [text-wrap:pretty]">
                Save a paper from its page and it lands here, with the decode
                that was on it at the time.
              </p>
            </div>
          )}

          {data?.papers.map((p) => (
            <article
              key={p.arxiv_id}
              className="row-shift group border-b border-border last:border-b-0"
            >
              <Link href={`/paper/${p.arxiv_id}`} className="block py-6">
                <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[11.5px] tracking-[0.1em] text-subtle">
                  <span>{p.arxiv_id}</span>
                  <span aria-hidden="true">·</span>
                  <span className="tnum">{relativeTime(p.published_at)}</span>
                  {p.is_decoded && (
                    <span className="border border-accent-soft px-[7px] py-[3px] text-[10.5px] uppercase tracking-[0.12em] text-accent">
                      Decoded
                    </span>
                  )}
                </div>

                <h2 className="mb-2.5 max-w-[44ch] font-serif text-[21px] font-semibold leading-[1.3] tracking-[-0.012em] transition-colors [text-wrap:pretty] group-hover:text-accent">
                  {p.title}
                </h2>

                {p.one_sentence && (
                  <p className="max-w-[56ch] text-[16.5px] leading-[1.5] text-muted-foreground [text-wrap:pretty]">
                    {p.one_sentence}
                  </p>
                )}
              </Link>
            </article>
          ))}
        </div>
      </Column>

      <Rail>
        <RailHeading>What is kept</RailHeading>
        <RailNote>
          Saving a paper keeps the link, not a copy. When a paper gets more
          layers decoded, the saved entry gets them too.
        </RailNote>
      </Rail>
    </PageShell>
  );
}
