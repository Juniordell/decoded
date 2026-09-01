"use client";

import { useEffect, useRef } from "react";
import { EVENTS, capture } from "@/lib/analytics";

/**
 * Dispara um evento quando uma seção entra em tela pela primeira vez.
 *
 * Isso separa quem abriu de quem leu. Um usuário que chega em "deep dive"
 * teve uma sessão qualitativamente diferente de quem viu só o TL;DR.
 */
export function SectionTracker({
  arxivId,
  sectionIds,
}: {
  arxivId: string;
  sectionIds: string[];
}) {
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const id = entry.target.id;
          if (seen.current.has(id)) continue;
          seen.current.add(id);
          capture(EVENTS.PAPER_SECTION_VIEWED, {
            arxiv_id: arxivId,
            section: id,
            depth: seen.current.size,
          });
        }
      },
      { threshold: 0.4 },
    );

    for (const id of sectionIds) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, [arxivId, sectionIds]);

  return null;
}