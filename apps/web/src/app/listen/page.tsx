import type { Metadata } from "next";
import Link from "next/link";
import { CopyField } from "@/components/copy-field";
import {
  Column,
  PageLead,
  PageShell,
  PageTitle,
  Rail,
  RailHeading,
  RailNote,
  WhereItBreaks,
} from "@/components/page-shell";

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
    <PageShell>
      <Column>
        <PageTitle className="mb-[22px]">Listen</PageTitle>
        <PageLead className="mb-[clamp(36px,4.5vw,52px)] max-w-[54ch]">
          Every decoded paper as three to eight minutes of audio. Written for
          the ear — no diagrams, no notation, nothing you need to see.
        </PageLead>

        <div className="mb-[clamp(44px,5vw,64px)] bg-surface px-[26px] py-6">
          <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
            Subscribe
          </p>
          <p className="mb-4 text-[17px] text-muted-foreground">
            Paste this into Overcast, Pocket Casts, or any podcast app.
          </p>
          <CopyField value={`${SITE_URL}/feed.xml`} />
        </div>

        <div className="border-b border-rule-strong pb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          Latest episodes
        </div>

        {episodes.length === 0 ? (
          <p className="border-b border-border py-12 font-mono text-[11.5px] uppercase tracking-[0.14em] text-subtle">
            No episodes yet
          </p>
        ) : (
          <div>
            {episodes.map((ep) => (
              <div
                key={ep.arxiv_id}
                className="row-shift group border-b border-border last:border-b-0"
              >
                <Link
                  href={`/paper/${ep.arxiv_id}#podcast`}
                  className="flex flex-wrap items-start gap-x-6 gap-y-3.5 py-[26px]"
                >
                  <span
                    aria-hidden="true"
                    className="mt-1 flex h-[34px] w-[34px] flex-none items-center justify-center border border-accent font-mono text-[11px] text-accent transition-colors group-hover:bg-accent group-hover:text-accent-foreground"
                  >
                    ▶
                  </span>

                  <div className="min-w-0 flex-[1_1_340px]">
                    <div className="mb-2 flex flex-wrap items-center gap-x-3 font-mono text-[11.5px] tracking-[0.1em] text-subtle">
                      <span>{ep.arxiv_id}</span>
                      <span aria-hidden="true">·</span>
                      <span className="tnum">
                        {new Date(ep.published_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                    </div>

                    <h2 className="mb-2 max-w-[40ch] font-serif text-[21px] font-semibold leading-[1.3] transition-colors [text-wrap:pretty] group-hover:text-accent">
                      {ep.title}
                    </h2>

                    {ep.one_sentence && (
                      <p className="max-w-[52ch] text-[16.5px] leading-[1.5] text-muted-foreground [text-wrap:pretty]">
                        {ep.one_sentence}
                      </p>
                    )}
                  </div>

                  <span className="tnum ml-auto flex-none font-mono text-[12px] text-subtle">
                    {Math.round(ep.duration_seconds / 60)} min
                  </span>
                </Link>
              </div>
            ))}
          </div>
        )}
      </Column>

      <Rail>
        <RailHeading>Written for the ear</RailHeading>
        <RailNote>
          The audio script is not the article read aloud. Equations become
          sentences, figures become descriptions, and section numbers are
          dropped.
        </RailNote>
        <WhereItBreaks className="mt-[22px]">
          Diagram-heavy papers lose the most. When a figure carries the
          argument, the episode says so and points you back to the page.
        </WhereItBreaks>
      </Rail>
    </PageShell>
  );
}
