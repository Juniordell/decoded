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
    const a = await api.getAuthor(slug);
    return {
      title: a.name,
      description: `${a.paper_count} papers by ${a.name}${
        a.affiliation ? ` at ${a.affiliation}` : ""
      }, decoded for humans.`,
    };
  } catch {
    return { title: "Author not found", robots: { index: false } };
  }
}

function formatYear(iso: string | null): string {
  return iso ? new Date(iso).getFullYear().toString() : "—";
}

export default async function AuthorPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let author;
  try {
    author = await api.getAuthor(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const topics = author.topics ?? [];
  const coauthors = author.coauthors ?? [];
  const papers = author.papers ?? [];

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <Link
        href="/authors"
        className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:text-accent"
      >
        ← Authors
      </Link>

      <div className="mt-5 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="font-serif text-[32px] leading-tight tracking-tight">
            {author.name}
          </h1>
          {author.affiliation && (
            <p className="mt-2 text-[15px] text-muted-foreground">
              {author.institution_slug ? (
                <Link
                  href={`/institution/${author.institution_slug}`}
                  className="transition-colors hover:text-accent"
                >
                  {author.affiliation}
                </Link>
              ) : (
                author.affiliation
              )}
            </p>
          )}
        </div>
        <div className="shrink-0">
          <FollowButton
            targetType="author"
            slug={author.slug}
            initialFollowing={author.is_following}
          />
        </div>
      </div>

      {!author.is_disambiguated && (
        <p className="mt-4 border-l-2 border-border pl-3 text-[12px] leading-relaxed text-muted-foreground">
          Grouped by name. Papers by different researchers with the same name
          may appear together.
        </p>
      )}

      <div className="mt-8 grid grid-cols-3 gap-6 border-y border-border py-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Papers
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {author.paper_count}
          </p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Citations
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {author.total_citations}
          </p>
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Active
          </p>
          <p className="tnum mt-1 font-serif text-2xl leading-none">
            {formatYear(author.first_paper_at)}
            {formatYear(author.first_paper_at) !==
              formatYear(author.latest_paper_at) &&
              `–${formatYear(author.latest_paper_at)}`}
          </p>
        </div>
      </div>

      {topics.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Works on
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

      {coauthors.length > 0 && (
        <section className="mt-10 border-t border-border pt-8">
          <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Frequent collaborators
          </h2>
          <div className="space-y-1.5">
            {coauthors.map((c) => (
              <div
                key={c.slug}
                className="flex items-baseline justify-between gap-4"
              >
                <Link
                  href={`/author/${c.slug}`}
                  className="truncate text-[14px] transition-colors hover:text-accent"
                >
                  {c.name}
                </Link>
                <span className="tnum shrink-0 font-mono text-[11px] text-muted-foreground">
                  {c.shared_papers} together
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="mt-10 border-t border-border pt-8">
        <h2 className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Papers
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
