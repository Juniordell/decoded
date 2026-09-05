"use client";

import { useEffect, useRef, useState } from "react";
import type { DiagramMode } from "@/lib/mode-types";

let mermaidInitialized = false;

export function DiagramModeView({ data }: { data: DiagramMode }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      const mermaid = (await import("mermaid")).default;

      if (!mermaidInitialized) {
        mermaid.initialize({
          startOnLoad: false,
          theme: "base",
          securityLevel: "strict",
          themeVariables: {
            fontFamily: "var(--font-sans), sans-serif",
            fontSize: "14px",
            primaryColor: "#E7E4DA",
            primaryTextColor: "#16191A",
            primaryBorderColor: "#C4D6C9",
            lineColor: "#14573C",
            secondaryColor: "#E9F0EB",
            tertiaryColor: "#F7F6F1",
          },
        });
        mermaidInitialized = true;
      }

      try {
        const id = `mermaid-${Math.random().toString(36).slice(2)}`;
        const { svg: rendered } = await mermaid.render(id, data.mermaid);
        if (!cancelled) {
          setSvg(rendered);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to render");
        }
      }
    }

    void render();
    return () => {
      cancelled = true;
    };
  }, [data.mermaid]);

  return (
    <div className="space-y-6">
      <p className="max-w-[62ch] leading-[1.6] text-muted-foreground [text-wrap:pretty]">
        {data.caption}
      </p>

      <div
        ref={containerRef}
        className="overflow-x-auto bg-surface p-6"
      >
        {svg && (
          <div
            className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        )}

        {error && (
          <div>
            <p className="font-mono text-[11.5px] uppercase tracking-[0.14em] text-destructive">
              Diagram failed to render
            </p>
            <pre className="mt-3 overflow-x-auto font-mono text-[13px] leading-[1.7] text-muted-foreground">
              {data.mermaid}
            </pre>
          </div>
        )}

        {!svg && !error && <div className="h-48 animate-pulse bg-border/60" />}
      </div>

      {data.walkthrough.length > 0 && (
        <ol className="space-y-3">
          {data.walkthrough.map((step, i) => (
            <li key={i} className="grid gap-2 sm:grid-cols-[38px_1fr]">
              <span className="tnum font-mono text-[11.5px] text-subtle">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="max-w-[62ch] leading-[1.6]">{step}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
