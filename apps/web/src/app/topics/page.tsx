import type { Metadata } from "next";
import Link from "next/link";
import { TopicCard } from "@/components/topics/topic-card";
import { api } from "@/lib/api";

export const revalidate = 1800;

export const metadata: Metadata = {
  title: "Topics",
  description: "Every research topic Decoded tracks, discovered by clustering.",
};

const SORTS = [
  { key: "size", label: "Size" },
  { key: "momentum", label: "Momentum" },
  { key: "name", label: "A-Z" },
] as const;

export default async function TopicsPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort = "size" } = await searchParams;

  const data = await api.getTopics({ sort, limit: 200 });

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="font-serif text-4xl leading-tight tracking-tight">
          Topics
        </h1>
        <Link
          href="/pulse"
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:underline"
        >
          Field Pulse →
        </Link>
      </div>

      <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
        {data.total} topics, discovered by clustering paper embeddings rather
        than assigned by hand.
      </p>

      <div className="mt-8 flex gap-5 border-b border-border pb-3 font-mono text-[11px] uppercase tracking-[0.14em]">
        {SORTS.map((s) => (
          <Link
            key={s.key}
            href={`/topics?sort=${s.key}`}
            className={
              sort === s.key
                ? "text-foreground"
                : "text-muted-foreground transition-colors hover:text-foreground"
            }
          >
            {s.label}
          </Link>
        ))}
      </div>

      <div className="mt-2">
        {(data.topics ?? []).map((t) => (
          <TopicCard key={t.slug} topic={t} />
        ))}
      </div>
    </main>
  );
}
