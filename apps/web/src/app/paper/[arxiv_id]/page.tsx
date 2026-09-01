import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  AnalogiesBlock,
  DeepDiveBlock,
  FiguresBlock,
  OneSentenceBlock,
  Section,
  SixtySecondBlock,
  VocabularyBlock,
} from "@/components/decoded-sections";
import { OriginalAbstract } from "@/components/original-abstract";
import { PaperNav, type NavItem } from "@/components/paper-nav";
import { ApiError, api } from "@/lib/api";
import { decoded } from "@/lib/decoded-types";
import { categoryShort, compactNumber, relativeTime } from "@/lib/format";
import { SaveButton } from "@/components/save-button";
import { PaperJsonLd } from "@/components/paper-json-ld";
import { ModeSwitcher } from "@/components/modes/mode-switcher";
import { SectionTracker } from "@/components/section-tracker";
import { PodcastSection } from "@/components/podcast/podcast-section";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ arxiv_id: string }>;
}): Promise<Metadata> {
  const { arxiv_id } = await params;

  try {
    const paper = await api.getPaper(arxiv_id);
    const decodedMap = paper.decoded ?? {};
    const one = decoded.oneSentence(decodedMap);
    const description = one?.text ?? paper.abstract.slice(0, 155);
    const url = `/paper/${arxiv_id}`;

    return {
      title: paper.title,
      description,
      alternates: {
        canonical: url,
      },
      openGraph: {
        title: paper.title,
        description,
        type: "article",
        url,
        publishedTime: paper.published_at,
        authors: (paper.authors ?? []).map((a) => a.name),
        tags: paper.categories ?? [],
      },
      twitter: {
        card: "summary_large_image",
        title: paper.title,
        description,
      },
    };
  } catch {
    return {
      title: "Paper not found",
      robots: { index: false, follow: false },
    };
  }
}

export default async function PaperPage({
  params,
}: {
  params: Promise<{ arxiv_id: string }>;
}) {
  const { arxiv_id } = await params;

  let paper;
  try {
    paper = await api.getPaper(arxiv_id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const decodedMap = paper.decoded ?? {};

  const one = decoded.oneSentence(decodedMap);
  const sixty = decoded.sixtySecond(decodedMap);
  const deep = decoded.deepDive(decodedMap);
  const figures = decoded.figures(decodedMap);
  const analogies = decoded.analogies(decodedMap);
  const vocab = decoded.vocabulary(decodedMap);

  const terms = vocab?.terms ?? [];
  const isDecoded = Object.keys(decodedMap).length > 0;

  const navItems: NavItem[] = [
    one && { id: "tldr", label: "TL;DR" },
    sixty && { id: "sixty", label: "60 seconds" },
    deep && { id: "deep", label: "Deep dive" },
    figures?.items.length && { id: "figures", label: "Figures" },
    analogies?.items.length && { id: "analogies", label: "Analogies" },
    terms.length && { id: "vocabulary", label: "Vocabulary" },
    { id: "modes", label: "Modes" },
    { id: "podcast", label: "Listen" },
  ].filter(Boolean) as NavItem[];

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <PaperJsonLd paper={paper} oneSentence={one?.text ?? null} />
      <SectionTracker
        arxivId={paper.arxiv_id}
        sectionIds={navItems.map((n) => n.id)}
      />
      <div className="grid gap-12 lg:grid-cols-[1fr_160px]">
        <article className="min-w-0 max-w-2xl">
          <header className="mb-10">
            <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              <span>{paper.arxiv_id}</span>
              <span className="tnum">{relativeTime(paper.published_at)}</span>
              {(paper.categories ?? []).slice(0, 3).map((c) => (
                <span key={c} className="text-muted-foreground/70">
                  {categoryShort(c)}
                </span>
              ))}
            </div>

            <h1 className="font-serif text-[32px] leading-[1.2] tracking-tight sm:text-[38px]">
              {paper.title}
            </h1>

            {paper.authors && paper.authors.length > 0 && (
              <p className="mt-4 text-[13px] leading-relaxed text-muted-foreground">
                {paper.authors
                  .slice(0, 6)
                  .map((a) => a.name)
                  .join(", ")}
                {paper.authors.length > 6 && ` +${paper.authors.length - 6}`}
              </p>
            )}

            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              {paper.citation_count > 0 && (
                <span className="tnum">
                  {compactNumber(paper.citation_count)} citations
                </span>
              )}

              {paper.hn_url ? (
                <a
                  href={paper.hn_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="transition-colors hover:text-accent"
                >
                  HN x{paper.hn_mentions}
                </a>
              ) : (
                paper.hn_mentions > 0 && <span>HN x{paper.hn_mentions}</span>
              )}

              <a
                href={paper.pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="transition-colors hover:text-accent"
              >
                PDF
              </a>
              <SaveButton arxivId={paper.arxiv_id} />
            </div>
          </header>

          {!isDecoded && (
            <div className="border border-border bg-secondary/40 p-6">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Not decoded yet
              </p>
              <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
                This paper hasn&apos;t been decoded. The original abstract is
                below.
              </p>
            </div>
          )}

          <div className="space-y-10">
            {one && (
              <section id="tldr" className="scroll-mt-24">
                <OneSentenceBlock data={one} />
              </section>
            )}

            <PodcastSection arxivId={paper.arxiv_id} />

            {sixty && (
              <Section id="sixty" label="60-second read">
                <SixtySecondBlock data={sixty} terms={terms} />
              </Section>
            )}

            {deep && (
              <Section id="deep" label="Deep dive">
                <DeepDiveBlock data={deep} terms={terms} />
              </Section>
            )}

            {figures && figures.items.length > 0 && (
              <Section id="figures" label="Figures explained">
                <FiguresBlock data={figures} />
              </Section>
            )}

            {analogies && analogies.items.length > 0 && (
              <Section id="analogies" label="Analogies">
                <AnalogiesBlock data={analogies} />
              </Section>
            )}

            {vocab && vocab.terms.length > 0 && (
              <Section id="vocabulary" label="Vocabulary">
                <VocabularyBlock data={vocab} />
              </Section>
            )}

            <ModeSwitcher arxivId={paper.arxiv_id} />

            <OriginalAbstract abstract={paper.abstract} />
          </div>

          <div className="mt-12 border-t border-border pt-8">
            <Link
              href="/"
              className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:text-accent"
            >
              ← Back to feed
            </Link>
          </div>
        </article>

        {navItems.length > 0 && (
          <aside>
            <PaperNav items={navItems} />
          </aside>
        )}
      </div>
    </main>
  );
}
