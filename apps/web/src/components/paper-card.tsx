"use client";

import Link from "next/link";
import type { PaperCard as PaperCardType } from "@/lib/api";
import { EVENTS, capture } from "@/lib/analytics";
import { RelativeTime } from "@/components/relative-time";
import { Redacted } from "@/components/brand";
import { categoryShort, compactNumber } from "@/lib/format";

/**
 * Uma linha do feed. Sem card, sem sombra: fio de cabelo embaixo, e no hover
 * a linha desliza um pouco para a direita em vez de subir.
 */
export function PaperCard({
  paper,
  source = "feed",
  position,
}: {
  paper: PaperCardType;
  source?: string;
  position?: number;
}) {
  const categories = paper.categories ?? [];
  const authors = paper.authors ?? [];
  const decodedSections = paper.decoded_sections ?? [];

  return (
    <article className="row-shift group border-b border-border last:border-b-0">
      <Link
        href={`/paper/${paper.arxiv_id}`}
        className="block py-[26px]"
        onClick={() =>
          capture(EVENTS.PAPER_VIEWED, {
            arxiv_id: paper.arxiv_id,
            source,
            position,
            is_decoded: paper.is_decoded,
            priority_score: paper.priority_score,
          })
        }
      >
        <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[11.5px] tracking-[0.1em] text-subtle">
          <span>{paper.arxiv_id}</span>
          <span aria-hidden="true">·</span>
          <RelativeTime iso={paper.published_at} className="tnum" />
          {categories.slice(0, 2).map((c) => (
            <span key={c}>
              <span aria-hidden="true" className="mr-3">
                ·
              </span>
              {categoryShort(c)}
            </span>
          ))}

          {paper.is_decoded && (
            <span className="border border-accent-soft px-[7px] py-[3px] text-[10.5px] uppercase tracking-[0.12em] text-accent">
              Decoded
              {decodedSections.length > 0 && ` · ${decodedSections.length} layers`}
            </span>
          )}
        </div>

        <h2 className="mb-2.5 max-w-[44ch] font-serif text-[22px] font-semibold leading-[1.28] tracking-[-0.012em] transition-colors [text-wrap:pretty] group-hover:text-accent">
          {paper.title}
        </h2>

        {paper.one_sentence ? (
          <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
            <p className="max-w-[56ch] flex-[1_1_340px] text-[16.5px] leading-[1.5] text-muted-foreground [text-wrap:pretty]">
              {paper.one_sentence}
            </p>
            {paper.hn_mentions > 0 && (
              <span className="tnum ml-auto font-mono text-[12px] text-subtle">
                HN ×{paper.hn_mentions}
              </span>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
            <Redacted seed={position ?? 0} />
            <span className="font-mono text-[11.5px] uppercase tracking-[0.14em] text-muted-foreground">
              Not decoded yet
            </span>
            {paper.hn_mentions > 0 && (
              <span className="tnum ml-auto font-mono text-[12px] text-subtle">
                HN ×{paper.hn_mentions}
              </span>
            )}
          </div>
        )}

        {(authors.length > 0 || paper.citation_count > 0) && (
          <div className="mt-3.5 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-[11.5px] text-subtle">
            {authors.length > 0 && (
              <span className="min-w-0 truncate">
                {authors[0]}
                {authors.length > 1 && ` +${authors.length - 1}`}
              </span>
            )}

            {paper.citation_count > 0 && (
              <span className="tnum">
                {compactNumber(paper.citation_count)} citations
              </span>
            )}
          </div>
        )}
      </Link>
    </article>
  );
}

export function PaperCardSkeleton() {
  return (
    <div className="border-b border-border py-[26px] last:border-b-0">
      <div className="mb-2.5 h-3 w-40 animate-pulse bg-surface" />
      <div className="h-7 w-4/5 animate-pulse bg-surface" />
      <div className="mt-3 h-4 w-full animate-pulse bg-surface" />
      <div className="mt-2 h-4 w-2/3 animate-pulse bg-surface" />
      <div className="mt-4 h-3 w-48 animate-pulse bg-surface" />
    </div>
  );
}
