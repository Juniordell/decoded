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
import { Column, PageShell, Rail } from "@/components/page-shell";
import { Redacted } from "@/components/brand";
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
    <>
      <PaperJsonLd paper={paper} oneSentence={one?.text ?? null} />
      <SectionTracker
        arxivId={paper.arxiv_id}
        sectionIds={navItems.map((n) => n.id)}
      />

      <PageShell tight>
        <Column>
          <Link
            href="/"
            className="inline-block border-b border-accent-light pb-0.5 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
          >
            ← Feed
          </Link>

          <header className="mt-7">
            <div className="mb-3.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 font-mono text-[11.5px] tracking-[0.1em] text-subtle">
              <span>{paper.arxiv_id}</span>
              <span aria-hidden="true">·</span>
              <span className="tnum">{relativeTime(paper.published_at)}</span>
              {(paper.categories ?? []).slice(0, 3).map((c) => (
                <span key={c}>
                  <span aria-hidden="true" className="mr-3">
                    ·
                  </span>
                  {categoryShort(c)}
                </span>
              ))}
            </div>

            <h1 className="max-w-[26ch] font-serif text-[clamp(32px,4.2vw,52px)] font-semibold leading-[1.08] tracking-[-0.024em] [text-wrap:pretty]">
              {paper.title}
            </h1>

            {paper.authors && paper.authors.length > 0 && (
              <p className="mt-5 max-w-[62ch] font-mono text-[12px] leading-[1.7] text-muted-foreground">
                {paper.authors
                  .slice(0, 6)
                  .map((a) => a.name)
                  .join(", ")}
                {paper.authors.length > 6 && ` +${paper.authors.length - 6}`}
              </p>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2.5 border-b border-rule-strong pb-3.5 font-mono text-[11.5px] uppercase tracking-[0.14em]">
              {paper.citation_count > 0 && (
                <span className="tnum text-subtle">
                  {compactNumber(paper.citation_count)} citations
                </span>
              )}

              {paper.hn_url ? (
                <a
                  href={paper.hn_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="tnum border-b border-accent-light text-accent transition-colors hover:border-accent"
                >
                  HN ×{paper.hn_mentions}
                </a>
              ) : (
                paper.hn_mentions > 0 && (
                  <span className="tnum text-subtle">
                    HN ×{paper.hn_mentions}
                  </span>
                )
              )}

              <a
                href={paper.pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="border-b border-accent-light text-accent transition-colors hover:border-accent"
              >
                PDF
              </a>
              <SaveButton arxivId={paper.arxiv_id} />
            </div>
          </header>

          {!isDecoded && (
            <div className="mt-[clamp(36px,4.5vw,52px)] bg-surface px-7 py-[26px]">
              <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
                Not decoded yet
              </p>
              <Redacted width={280} className="mb-[18px]" />
              <p className="max-w-[56ch] text-[17px] leading-[1.55] [text-wrap:pretty]">
                This paper is in the queue. The original abstract is at the
                bottom of the page, and opening it here moves it up.
              </p>
            </div>
          )}

          <div className="mt-[clamp(36px,4.5vw,52px)] max-w-[70ch]">
            {one && (
              <section id="tldr" className="scroll-mt-28">
                <h2 className="mb-3.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
                  One sentence
                </h2>
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
        </Column>

        {navItems.length > 0 && (
          <Rail>
            <PaperNav items={navItems} />
          </Rail>
        )}
      </PageShell>
    </>
  );
}
