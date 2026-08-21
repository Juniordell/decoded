import Link from "next/link";
import type { PaperCard as PaperCardType } from "@/lib/api";
import { categoryShort, compactNumber, relativeTime } from "@/lib/format";

export function PaperCard({ paper }: { paper: PaperCardType }) {
  return (
    <article className="group border-b border-border py-7 last:border-b-0">
      <Link href={`/paper/${paper.arxiv_id}`} className="block">
        {/* Metadados de topo */}
        <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          <span className="tnum">{relativeTime(paper.published_at)}</span>

          {paper.categories.slice(0, 2).map((c) => (
            <span key={c} className="text-muted-foreground/70">
              {categoryShort(c)}
            </span>
          ))}

          {paper.is_decoded && (
            <span className="text-accent">
              decoded · {paper.decoded_sections.length}
            </span>
          )}
        </div>

        {/* Título */}
        <h2 className="font-serif text-[22px] leading-[1.25] tracking-tight transition-colors group-hover:text-accent sm:text-2xl">
          {paper.title}
        </h2>

        {/* One-sentence, ou fallback */}
        {paper.one_sentence ? (
          <p className="mt-2.5 text-[15px] leading-relaxed text-muted-foreground">
            {paper.one_sentence}
          </p>
        ) : (
          <p className="mt-2.5 font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground/50">
            Not decoded yet
          </p>
        )}

        {/* Rodapé: autores + sinais */}
        <div className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground/80">
          {paper.authors.length > 0 && (
            <span className="truncate">
              {paper.authors[0]}
              {paper.authors.length > 1 && (
                <span className="text-muted-foreground/60">
                  {" "}
                  +{paper.authors.length - 1}
                </span>
              )}
            </span>
          )}

          {paper.citation_count > 0 && (
            <span className="tnum">
              {compactNumber(paper.citation_count)} citations
            </span>
          )}

          {paper.hn_mentions > 0 && (
            <span className="tnum">HN ×{paper.hn_mentions}</span>
          )}
        </div>
      </Link>
    </article>
  );
}

export function PaperCardSkeleton() {
  return (
    <div className="border-b border-border py-7 last:border-b-0">
      <div className="mb-2.5 h-2.5 w-32 animate-pulse rounded bg-muted" />
      <div className="h-6 w-4/5 animate-pulse rounded bg-muted" />
      <div className="mt-3 h-4 w-full animate-pulse rounded bg-muted" />
      <div className="mt-1.5 h-4 w-2/3 animate-pulse rounded bg-muted" />
      <div className="mt-4 h-3 w-48 animate-pulse rounded bg-muted" />
    </div>
  );
}