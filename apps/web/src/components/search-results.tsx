import Link from "next/link";
import type { SearchHit } from "@/lib/api";
import { relativeTime } from "@/lib/format";

export function SearchResults({
  hits,
  reranked,
  latencyMs,
  totalFound,
}: {
  hits: SearchHit[];
  reranked: boolean;
  latencyMs: number;
  totalFound: number;
}) {
  if (hits.length === 0) {
    return (
      <p className="py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
        No results
      </p>
    );
  }

  return (
    <>
      <p className="mt-8 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground/60">
        {hits.length} of {totalFound} candidates
        {reranked && " · reranked"}
        {" · "}
        <span className="tnum">{latencyMs}ms</span>
      </p>

      <div className="mt-2">
        {hits.map((hit, i) => (
          <article
            key={hit.arxiv_id}
            className="border-b border-border py-6 last:border-b-0"
          >
            <Link href={`/paper/${hit.arxiv_id}`} className="group block">
              <div className="mb-2 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <span className="tnum text-muted-foreground/50">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="tnum">{relativeTime(hit.published_at)}</span>
                {hit.section && (
                  <span className="text-accent">{hit.section}</span>
                )}
                <span className="tnum ml-auto text-muted-foreground/40">
                  {hit.score.toFixed(3)}
                </span>
              </div>

              <h2 className="font-serif text-xl leading-snug tracking-tight transition-colors group-hover:text-accent">
                {hit.title}
              </h2>

              {hit.one_sentence && (
                <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
                  {hit.one_sentence}
                </p>
              )}

              {hit.snippet && (
                <p className="mt-3 border-l-2 border-accent/25 pl-4 text-[13px] leading-relaxed text-foreground/70">
                  {hit.snippet.length > 320
                    ? `${hit.snippet.slice(0, 320)}…`
                    : hit.snippet}
                </p>
              )}
            </Link>
          </article>
        ))}
      </div>
    </>
  );
}
