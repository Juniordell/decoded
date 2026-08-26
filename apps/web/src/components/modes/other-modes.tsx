"use client";

import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { AnalogyMode, CodeMode, StoryMode } from "@/lib/mode-types";

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
      <p className="text-[15px] leading-relaxed">{data.what_it_does}</p>

      <div>
        <div className="flex items-center justify-between border border-b-0 border-border bg-secondary/40 px-4 py-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            {data.language}
          </span>
          <button
            type="button"
            onClick={copy}
            className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:text-accent"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>

        <div className="overflow-x-auto border border-border">
          <SyntaxHighlighter
            language={data.language}
            style={oneDark}
            customStyle={{
              margin: 0,
              borderRadius: 0,
              fontSize: "13px",
              background: "#050D1A",
            }}
          >
            {data.code}
          </SyntaxHighlighter>
        </div>
      </div>

      {data.example_usage && (
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
            Example
          </p>
          <div className="overflow-x-auto border border-border">
            <SyntaxHighlighter
              language={data.language}
              style={oneDark}
              customStyle={{
                margin: 0,
                borderRadius: 0,
                fontSize: "13px",
                background: "#050D1A",
              }}
            >
              {data.example_usage}
            </SyntaxHighlighter>
          </div>
        </div>
      )}

      {data.caveats.length > 0 && (
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Simplified from the paper
          </p>
          <ul className="space-y-1.5">
            {data.caveats.map((c, i) => (
              <li
                key={i}
                className="relative pl-4 text-[14px] leading-relaxed text-muted-foreground"
              >
                <span className="absolute left-0 text-accent">›</span>
                {c}
              </li>
            ))}
          </ul>
        </div>
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
          <div className="mb-3 flex flex-wrap items-baseline gap-x-3">
            <h3 className="font-serif text-xl leading-snug tracking-tight">
              {a.concept}
            </h3>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
              via {a.domain}
            </span>
          </div>

          <p className="text-[15px] leading-relaxed">{a.setup}</p>

          {a.mapping.length > 0 && (
            <div className="mt-5 space-y-1.5 border-l-2 border-accent/25 pl-5">
              {a.mapping.map((m, j) => {
                const [from, ...to] = m.split("→");
                return (
                  <div
                    key={j}
                    className="grid gap-1 text-[14px] sm:grid-cols-2 sm:gap-4"
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

          <p className="mt-5 text-[14px] leading-relaxed text-muted-foreground">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
              Where it breaks ·{" "}
            </span>
            {a.where_it_breaks}
          </p>
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
          <div key={i} className="grid gap-3 sm:grid-cols-[64px_1fr] sm:gap-6">
            <div className="tnum pt-1 font-mono text-[11px] text-accent">
              {beat.year ?? "—"}
            </div>
            <div>
              <h3 className="mb-2 font-serif text-xl leading-snug tracking-tight">
                {beat.heading}
              </h3>
              <p className="text-[15px] leading-relaxed text-foreground/90">
                {beat.body}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-10 border-t border-border pt-6">
        <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
          Where it leaves us
        </p>
        <p className="text-[15px] leading-relaxed">{data.where_it_leaves_us}</p>
      </div>
    </div>
  );
}
