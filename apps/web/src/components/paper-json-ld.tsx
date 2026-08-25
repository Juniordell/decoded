import type { PaperDetail } from "@/lib/api";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export function PaperJsonLd({
  paper,
  oneSentence,
}: {
  paper: PaperDetail;
  oneSentence: string | null;
}) {
  const schema = {
    "@context": "https://schema.org",
    "@type": "ScholarlyArticle",
    headline: paper.title,
    abstract: oneSentence ?? paper.abstract.slice(0, 300),
    datePublished: paper.published_at,
    author: (paper.authors ?? []).map((a) => ({
      "@type": "Person",
      name: a.name,
      ...(a.affiliation
        ? { affiliation: { "@type": "Organization", name: a.affiliation } }
        : {}),
    })),
    identifier: {
      "@type": "PropertyValue",
      propertyID: "arXiv",
      value: paper.arxiv_id,
    },
    url: `${SITE_URL}/paper/${paper.arxiv_id}`,
    sameAs: paper.pdf_url,
    publisher: {
      "@type": "Organization",
      name: "Decoded",
      url: SITE_URL,
    },
    ...(paper.citation_count > 0
      ? {
          interactionStatistic: {
            "@type": "InteractionCounter",
            interactionType: "https://schema.org/CiteAction",
            userInteractionCount: paper.citation_count,
          },
        }
      : {}),
    keywords: (paper.categories ?? []).join(", "),
    isAccessibleForFree: true,
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
