"use client";

import "katex/dist/katex.min.css";
import { BlockMath } from "react-katex";
import { WhereItBreaks } from "@/components/page-shell";
import type { MathMode } from "@/lib/mode-types";

export function MathModeView({ data }: { data: MathMode }) {
  return (
    <div className="space-y-8">
      <div>
        <p className="mb-2.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          The idea, before notation
        </p>
        <p className="max-w-[62ch] leading-[1.6] [text-wrap:pretty]">
          {data.intuition}
        </p>
      </div>

      {data.equations.length === 0 && (
        <p className="bg-surface px-6 py-5 text-[16px] text-muted-foreground">
          This paper has no load-bearing equations.
        </p>
      )}

      {data.equations.map((eq, i) => (
        <div key={i} className="border-t border-border pt-6">
          <p className="mb-3.5 font-mono text-[12px] tracking-[0.06em] text-accent">
            {eq.label}
          </p>

          <div className="overflow-x-auto bg-surface px-6 py-6">
            <ErrorBoundaryMath latex={eq.latex} />
          </div>

          <p className="mt-4 max-w-[62ch] leading-[1.6] [text-wrap:pretty]">
            <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-subtle">
              Read it as ·{" "}
            </span>
            {eq.plain_reading}
          </p>

          {eq.what_each_symbol_means.length > 0 && (
            <dl className="mt-5 space-y-2">
              {eq.what_each_symbol_means.map((entry, j) => {
                const [symbol, ...rest] = entry.split("—");
                return (
                  <div
                    key={j}
                    className="grid gap-1 sm:grid-cols-[110px_1fr] sm:gap-4"
                  >
                    <dt className="font-mono text-[13px] text-accent">
                      {symbol.trim()}
                    </dt>
                    <dd className="text-[16px] leading-[1.55] text-muted-foreground">
                      {rest.join("—").trim()}
                    </dd>
                  </div>
                );
              })}
            </dl>
          )}

          <p className="mt-4 max-w-[62ch] text-[16px] leading-[1.55] text-muted-foreground [text-wrap:pretty]">
            {eq.why_it_matters}
          </p>
        </div>
      ))}

      {data.the_trick && (
        <WhereItBreaks label="The trick">{data.the_trick}</WhereItBreaks>
      )}
    </div>
  );
}

/** KaTeX joga exceção em LaTeX inválido. Cai pro texto bruto. */
function ErrorBoundaryMath({ latex }: { latex: string }) {
  try {
    return <BlockMath math={latex} />;
  } catch {
    return (
      <code className="font-mono text-[14px] text-muted-foreground">
        {latex}
      </code>
    );
  }
}
