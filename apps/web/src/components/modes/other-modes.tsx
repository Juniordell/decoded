"use client";

import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { WhereItBreaks } from "@/components/page-shell";
import type { AnalogyMode, CodeMode, StoryMode } from "@/lib/mode-types";

// O bloco de código vive na segunda superfície, como todo inset do sistema.
// Nada de painel escuro no meio de uma página de leitura.
const CODE_STYLE = {
  margin: 0,
  borderRadius: 0,
  padding: "22px 24px",
  fontSize: "14px",
  lineHeight: 1.7,
  background: "transparent",
} as const;

/* ---------------------------------------------------------------- */
/* Code                                                              */
/* ---------------------------------------------------------------- */
export function CodeModeView({ data }: { data: CodeMode }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(data.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6">
      <p className="max-w-[62ch] leading-[1.6] [text-wrap:pretty]">
        {data.what_it_does}
      </p>

      <div className="bg-surface">
        <div className="flex items-center justify-between border-b border-border px-6 py-2.5">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-subtle">
            {data.language}
          </span>
          <button
            type="button"
            onClick={copy}
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent transition-opacity hover:opacity-70"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>

        <div className="overflow-x-auto">
          <SyntaxHighlighter
            language={data.language}
            style={oneLight}
            customStyle={CODE_STYLE}
          >
            {data.code}
          </SyntaxHighlighter>
        </div>
      </div>

      {data.example_usage && (
        <div>
          <p className="mb-2.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
            Example
          </p>
          <div className="overflow-x-auto bg-surface">
            <SyntaxHighlighter
              language={data.language}
              style={oneLight}
              customStyle={CODE_STYLE}
            >
              {data.example_usage}
            </SyntaxHighlighter>
          </div>
        </div>
      )}

      {data.caveats.length > 0 && (
        <WhereItBreaks label="Simplified from the paper">
          <ul className="space-y-2">
            {data.caveats.map((c, i) => (
              <li key={i} className="relative pl-5">
                <span aria-hidden="true" className="absolute left-0 text-accent">
                  ›
                </span>
                {c}
              </li>
            ))}
          </ul>
        </WhereItBreaks>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* Analogy                                                           */
/* ---------------------------------------------------------------- */
export function AnalogyModeView({ data }: { data: AnalogyMode }) {
  return (
    <div className="space-y-10">
      {data.analogies.map((a, i) => (
        <div
          key={i}
          className="border-t border-border pt-6 first:border-t-0 first:pt-0"
        >
          <div className="mb-3 flex flex-wrap items-baseline gap-x-3.5">
            <h3 className="font-serif text-[22px] font-semibold leading-[1.3] tracking-[-0.01em]">
              {a.concept}
            </h3>
            <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-subtle">
              via {a.domain}
            </span>
          </div>

          <p className="max-w-[62ch] leading-[1.6] [text-wrap:pretty]">
            {a.setup}
          </p>

          {a.mapping.length > 0 && (
            <div className="mt-5 space-y-2 bg-surface px-5 py-4">
              {a.mapping.map((m, j) => {
                const [from, ...to] = m.split("→");
                return (
                  <div
                    key={j}
                    className="grid gap-1 text-[15.5px] sm:grid-cols-2 sm:gap-5"
                  >
                    <span className="text-muted-foreground">{from.trim()}</span>
                    <span className="text-foreground">
                      {to.join("→").trim()}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          <WhereItBreaks className="mt-5">{a.where_it_breaks}</WhereItBreaks>
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* Story                                                             */
/* ---------------------------------------------------------------- */
export function StoryModeView({ data }: { data: StoryMode }) {
  return (
    <div>
      <div className="space-y-8">
        {data.beats.map((beat, i) => (
          <div key={i} className="grid gap-3 sm:grid-cols-[72px_1fr] sm:gap-6">
            <div className="tnum pt-2 font-mono text-[12px] text-subtle">
              {beat.year ?? "—"}
            </div>
            <div>
              <h3 className="mb-2.5 font-serif text-[22px] font-semibold leading-[1.3] tracking-[-0.01em]">
                {beat.heading}
              </h3>
              <p className="max-w-[62ch] leading-[1.6] [text-wrap:pretty]">
                {beat.body}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-10 border-t border-border pt-6">
        <p className="mb-2.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          Where it leaves us
        </p>
        <p className="max-w-[62ch] leading-[1.6] [text-wrap:pretty]">
          {data.where_it_leaves_us}
        </p>
      </div>
    </div>
  );
}
