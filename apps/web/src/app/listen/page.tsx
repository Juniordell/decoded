import type { Metadata } from "next";
import Link from "next/link";

const API_BASE = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Listen",
  description:
    "Every decoded paper as three to eight minutes of audio. Subscribe in any podcast app.",
};

interface Episode {
  arxiv_id: string;
  title: string;
  one_sentence: string | null;
  audio_url: string;
  duration_seconds: number;
  published_at: string;
}

async function getEpisodes(): Promise<Episode[]> {
  try {
    const res = await fetch(`${API_BASE}/v1/podcasts?limit=100`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    const data: { episodes: Episode[] } = await res.json();
    return data.episodes ?? [];
  } catch {
    return [];
  }
}

export default async function ListenPage() {
  const episodes = await getEpisodes();

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-serif text-4xl leading-tight tracking-tight sm:text-5xl">
        Listen
      </h1>
      <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
        Every decoded paper as three to eight minutes of audio. Written for the
        ear — no diagrams, no notation, nothing you need to see.
      </p>

      <div className="mt-8 border border-border p-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          Subscribe
        </p>
        <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
          Paste this into Overcast, Pocket Casts, or any podcast app.
        </p>
        <code className="mt-3 block overflow-x-auto bg-secondary/60 px-3 py-2 font-mono text-[12px]">
          {SITE_URL}/feed.xml
        </code>
      </div>

      {episodes.length === 0 ? (
        <p className="py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
          No episodes yet
        </p>
      ) : (
        <div className="mt-10">
          {episodes.map((ep) => (
            <Link
              key={ep.arxiv_id}
              href={`/paper/${ep.arxiv_id}#podcast`}
              className="group block border-b border-border py-5 last:border-b-0"
            >
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="font-serif text-lg leading-snug tracking-tight transition-colors group-hover:text-accent">
                  {ep.title}
                </h2>
                <span className="tnum shrink-0 font-mono text-[11px] text-muted-foreground">
                  {Math.round(ep.duration_seconds / 60)} min
                </span>
              </div>
              {ep.one_sentence && (
                <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
                  {ep.one_sentence}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}