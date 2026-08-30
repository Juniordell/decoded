import type { Metadata } from "next";
import Link from "next/link";
import { TopicCard } from "@/components/topics/topic-card";
import { api } from "@/lib/api";

export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Field Pulse",
  description:
    "What's heating up and cooling down in AI research. Topics discovered automatically from arXiv, tracked week over week.",
};

function Section({
  label,
  hint,
  topics,
}: {
  label: string;
  hint: string;
  topics: React.ComponentProps<typeof TopicCard>["topic"][];
}) {
  if (topics.length === 0) return null;

  return (
    <section className="border-t border-border pt-8">
      <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
        {label}
      </h2>
      <p className="mb-4 mt-1 text-[13px] text-muted-foreground">{hint}</p>
      <div>
        {topics.map((t) => (
          <TopicCard key={t.slug} topic={t} showKeywords={false} />
        ))}
      </div>
    </section>
  );
}

export default async function PulsePage() {
  let pulse;
  let error: string | null = null;

  try {
    pulse = await api.getPulse();
  } catch (e) {
    error = e instanceof Error ? e.message : "Unknown error";
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-serif text-4xl leading-tight tracking-tight sm:text-5xl">
        Field Pulse
      </h1>
      <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
        Topics discovered automatically from what researchers are actually
        publishing — not from a taxonomy someone wrote once. Tracked week over
        week.
      </p>

      {error && (
        <div className="mt-8 border border-destructive/40 bg-destructive/5 p-5">
          <p className="font-mono text-xs uppercase tracking-[0.14em] text-destructive">
            Pulse unavailable
          </p>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
        </div>
      )}

      {pulse && (
        <>
          <div className="mt-6 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            <span className="tnum">{pulse.total_topics} topics</span>
            <span className="tnum">{pulse.total_papers} papers</span>
            <span className="tnum">{pulse.weeks_covered} weeks tracked</span>
          </div>

          <div className="mt-12 space-y-10">
            <Section
              label="Heating up"
              hint="More papers in the last four weeks than the four before."
              topics={pulse.rising ?? []}
            />
            <Section
              label="Emerging"
              hint="New topics with no prior activity to compare against."
              topics={pulse.emerging ?? []}
            />
            <Section
              label="Cooling"
              hint="Fewer papers than the previous period."
              topics={pulse.cooling ?? []}
            />
            <Section
              label="Largest"
              hint="Most papers overall, regardless of trend."
              topics={pulse.largest ?? []}
            />
          </div>

          <div className="mt-12 border-t border-border pt-8">
            <Link
              href="/topics"
              className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:underline"
            >
              All {pulse.total_topics} topics →
            </Link>
          </div>
        </>
      )}
    </main>
  );
}
