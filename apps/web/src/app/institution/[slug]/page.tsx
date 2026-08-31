import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { FollowButton } from "@/components/follow-button";
import { PaperCard } from "@/components/paper-card";
import { ApiError, api } from "@/lib/api";

export const revalidate = 1800;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const i = await api.getInstitution(slug);
    return {
      title: i.name,
      description: `${i.paper_count} papers from ${i.name}, decoded for humans.`,
    };
  } catch {
    return { title: "Institution not found", robots: { index: false } };
  }
}

export default async function InstitutionPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let inst;
  try {
    inst = await api.getInstitution(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const authors = inst.top_authors ?? [];
  const topics = inst.topics ?? [];
  const papers = inst.papers ?? [];

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <Link
        href="/institutions"
        className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:text-accent"
      >
        ← Institutions
      </Link>

      <div className="mt-5 flex items-start justify-between gap-6">
        <h1 className="min-w-0 font-serif text-[32px] leading-tight tracking-tight">
          {inst.name}
        </h1>
        <div className="shrink-0">
          <FollowButton
            targetType="institution"
            slug={inst.slug}
            initialFollowing={inst.is_following}
          />
        </div>
      </div>

      <div className="mt-8 grid grid-cols-3 gap-6 border-y border-border py-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Papers
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {inst.paper_count}
          </p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Authors
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {inst.author_count}
          </p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Citations
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {inst.total_citations}
          </p>
        </div>
      </div>

      {topics.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Research areas
          </h2>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {topics.map((t) => (
              <Link
                key={t.slug}
                href={`/topic/${t.slug}`}
                className="text-[14px] transition-colors hover:text-accent"
              >
                {t.name}
                <span className="tnum ml-1.5 text-[11px] text-muted-foreground">
                  {t.paper_count}
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {authors.length > 0 && (
        <section className="mt-10 border-t border-border pt-8">
          <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Researchers
          </h2>
          <div className="space-y-1.5">
            {authors.map((a) => (
              <div
                key={a.slug}
                className="flex items-baseline justify-between gap-4"
              >
                <Link
                  href={`/author/${a.slug}`}
                  className="truncate text-[14px] transition-colors hover:text-accent"
                >
                  {a.name}
                </Link>
                <span className="tnum shrink-0 font-mono text-[11px] text-muted-foreground">
                  {a.paper_count} papers
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="mt-10 border-t border-border pt-8">
        <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Recent papers
        </h2>
        <div>
          {papers.map((p) => (
            <PaperCard key={p.arxiv_id} paper={p} />
          ))}
        </div>
      </section>
    </main>
  );
}
