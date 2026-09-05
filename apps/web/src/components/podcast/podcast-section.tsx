"use client";

import { useQuery } from "@tanstack/react-query";
import { Resolve } from "@/components/brand";
import { AudioPlayer } from "./audio-player";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/+$/, "");

interface PodcastResponse {
  arxiv_id: string;
  status: string;
  audio_url: string | null;
  duration_seconds: number | null;
  chapters: Array<{
    title: string;
    start_seconds: number;
    end_seconds: number;
  }>;
}

export function PodcastSection({ arxivId }: { arxivId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["podcast", arxivId],
    queryFn: async (): Promise<PodcastResponse> => {
      const res = await fetch(`${API_BASE}/v1/podcasts/${arxivId}`);
      if (!res.ok) throw new Error(String(res.status));
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
  });

  // Sem episódio pronto, a seção não existe — nada de placeholder vazio
  if (isLoading || !data || data.status !== "ready" || !data.audio_url) {
    return null;
  }

  const minutes = Math.round((data.duration_seconds ?? 0) / 60);

  return (
    <section id="podcast" className="scroll-mt-28">
      <Resolve className="mb-8 mt-[34px]" />
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          Listen
        </h2>
        <span className="tnum font-mono text-[11.5px] uppercase tracking-[0.14em] text-subtle">
          {minutes} min
        </span>
      </div>

      <AudioPlayer
        src={data.audio_url}
        arxivId={arxivId}
        chapters={data.chapters ?? []}
        duration={data.duration_seconds ?? undefined}
      />
    </section>
  );
}