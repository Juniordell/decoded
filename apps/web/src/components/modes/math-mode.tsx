"use client";

import "katex/dist/katex.min.css";
import { BlockMath } from "react-katex";
import type { MathMode } from "@/lib/mode-types";

export function MathModeView({ data }: { data: MathMode }) {
  return (
    <div className="space-y-8">
      <div>
        <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
          The idea, before notation
        </p>
        <p className="text-[15px] leading-relaxed">{data.intuition}</p>
      </div>

      {data.equations.length === 0 && (
        <p className="border border-border bg-secondary/40 p-4 text-[14px] text-muted-foreground">
          This paper has no load-bearing equations.
        </p>
      )}

      {data.equations.map((eq, i) => (
        <div key={i} className="border-t border-border pt-6">
          <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            {eq.label}
          </p>

          <div className="overflow-x-auto bg-secondary/40 px-5 py-6">
            <ErrorBoundaryMath latex={eq.latex} />
          </div>

          <p className="mt-4 text-[15px] leading-relaxed">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
              Read it as ·{" "}
            </span>
            {eq.plain_reading}
          </p>

          {eq.what_each_symbol_means.length > 0 && (
            <dl className="mt-4 space-y-1.5">
              {eq.what_each_symbol_means.map((entry, j) => {
                const [symbol, ...rest] = entry.split("—");
                return (
                  <div
                    key={j}
                    className="grid gap-1 sm:grid-cols-[80px_1fr] sm:gap-4"
                  >
                    <dt className="font-mono text-[13px] text-accent">
                      {symbol.trim()}
                    </dt>
                    <dd className="text-[14px] leading-relaxed text-foreground/85">
                      {rest.join("—").trim()}
                    </dd>
                  </div>
                );
              })}
            </dl>
          )}

          <p className="mt-4 text-[14px] leading-relaxed text-muted-foreground">
            {eq.why_it_matters}
          </p>
        </div>
      ))}

      {data.the_trick && (
        <div className="border-l-2 border-accent bg-secondary/40 py-4 pl-5">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
            The trick
          </p>
          <p className="text-[15px] leading-relaxed">{data.the_trick}</p>
        </div>
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
      <code className="font-mono text-[13px] text-muted-foreground">
        {latex}
      </code>
    );
  }
}
