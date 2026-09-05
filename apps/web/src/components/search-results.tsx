import Link from "next/link";
import type { SearchHit } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { EVENTS, capture } from "@/lib/analytics";

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
      <div className="mt-10 border-y border-border py-12">
        <p className="mb-3.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          No results
        </p>
        <p className="max-w-[46ch] font-serif text-[21px] leading-[1.45] [text-wrap:pretty]">
          Nothing in the decoded archive matched that. Search runs over the
          explanations, not the raw PDFs — a paper still in the queue will not
          show up here.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="mb-2 mt-10 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 border-b border-rule-strong pb-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          {hits.length} of {totalFound} candidates
        </span>
        <span className="tnum font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
          {reranked ? "Ranked by passage match" : "Ranked by similarity"} ·{" "}
          {latencyMs}ms
        </span>
      </div>

      <div>
        {hits.map((hit, i) => (
          <article
            key={hit.arxiv_id}
            className="row-shift group border-b border-border last:border-b-0"
          >
            <Link
              href={`/paper/${hit.arxiv_id}`}
              className="block py-6"
              onClick={() =>
                capture(EVENTS.SEARCH_RESULT_CLICKED, {
                  arxiv_id: hit.arxiv_id,
                  position: i,
                  score: hit.score,
                  from_chunk: !!hit.snippet,
                })
              }
            >
              <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 font-mono text-[11.5px] tracking-[0.1em] text-subtle">
                <span>{hit.arxiv_id}</span>
                <span aria-hidden="true">·</span>
                <span className="tnum">{relativeTime(hit.published_at)}</span>
                {hit.section && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>{hit.section}</span>
                  </>
                )}
                <span className="tnum ml-auto">
                  match {hit.score.toFixed(2)}
                </span>
              </div>

              <h2 className="mb-2.5 max-w-[44ch] font-serif text-[21px] font-semibold leading-[1.3] tracking-[-0.012em] transition-colors [text-wrap:pretty] group-hover:text-accent">
                {hit.title}
              </h2>

              {hit.one_sentence && (
                <p className="max-w-[56ch] text-[16.5px] leading-[1.55] text-muted-foreground [text-wrap:pretty]">
                  {hit.one_sentence}
                </p>
              )}

              {hit.snippet && (
                <p className="mt-3 max-w-[56ch] text-[16px] leading-[1.55] text-muted-foreground [text-wrap:pretty]">
                  Matched on{" "}
                  <span className="bg-accent-soft text-foreground">
                    {hit.snippet.length > 240
                      ? `${hit.snippet.slice(0, 240)}…`
                      : hit.snippet}
                  </span>
                </p>
              )}
            </Link>
          </article>
        ))}
      </div>
    </>
  );
}
