"use client";

import { useState } from "react";
import type { TopicPoint } from "@/lib/api";

const WIDTH = 640;
const HEIGHT = 180;
const PADDING = { top: 16, right: 8, bottom: 28, left: 8 };

export function TimelineChart({ points }: { points: TopicPoint[] }) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (points.length === 0) {
    return (
      <p className="border-y border-border py-10 font-mono text-[11.5px] uppercase tracking-[0.14em] text-subtle">
        No timeline data yet
      </p>
    );
  }

  const max = Math.max(...points.map((p) => p.papers), 1);
  const plotW = WIDTH - PADDING.left - PADDING.right;
  const plotH = HEIGHT - PADDING.top - PADDING.bottom;

  const barW = plotW / points.length;
  const gap = Math.min(4, barW * 0.2);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label="Papers per week"
      >
        {/* Linha de base */}
        <line
          x1={PADDING.left}
          y1={PADDING.top + plotH}
          x2={WIDTH - PADDING.right}
          y2={PADDING.top + plotH}
          className="stroke-border"
          strokeWidth={1}
        />

        {points.map((p, i) => {
          const h = (p.papers / max) * plotH;
          const x = PADDING.left + i * barW + gap / 2;
          const y = PADDING.top + plotH - h;
          const isHovered = hovered === i;

          return (
            <g key={p.week}>
              {/* Área de hover, cobre a coluna inteira */}
              <rect
                x={PADDING.left + i * barW}
                y={PADDING.top}
                width={barW}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
              />
              <rect
                x={x}
                y={y}
                width={barW - gap}
                height={Math.max(h, p.papers > 0 ? 2 : 0)}
                className={
                  isHovered
                    ? "fill-accent"
                    : "fill-accent-soft transition-colors"
                }
                pointerEvents="none"
              />
            </g>
          );
        })}

        {/* Rótulos: primeiro, meio, último */}
        {[0, Math.floor(points.length / 2), points.length - 1].map((i) => {
          const p = points[i];
          if (!p) return null;
          const d = new Date(p.week);
          return (
            <text
              key={`label-${i}`}
              x={PADDING.left + i * barW + barW / 2}
              y={HEIGHT - 8}
              textAnchor="middle"
              className="fill-[var(--subtle-foreground)] font-mono text-[10px] uppercase tracking-wider"
            >
              {d.toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </text>
          );
        })}
      </svg>

      {/* Tooltip */}
      {hovered !== null && points[hovered] && (
        <div
          className="pointer-events-none absolute top-0 border border-border bg-background px-3.5 py-2.5"
          style={{
            left: `${((hovered + 0.5) / points.length) * 100}%`,
            transform: "translateX(-50%)",
          }}
        >
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-subtle">
            {new Date(points[hovered].week).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })}
          </p>
          <p className="tnum mt-1 font-serif text-[22px] font-bold leading-none tracking-[-0.02em]">
            {points[hovered].papers}
            <span className="ml-2 font-mono text-[11px] font-normal text-subtle">
              papers
            </span>
          </p>
          {points[hovered].citations > 0 && (
            <p className="tnum mt-1.5 font-mono text-[11px] text-subtle">
              {points[hovered].citations} citations
            </p>
          )}
        </div>
      )}
    </div>
  );
}
