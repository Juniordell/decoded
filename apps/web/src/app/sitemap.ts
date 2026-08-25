import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const API_BASE = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

interface SitemapEntry {
  arxiv_id: string;
  updated_at: string;
  is_decoded: boolean;
}

export const revalidate = 3600;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: "hourly",
      priority: 1.0,
    },
    {
      url: `${SITE_URL}/search`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.5,
    },
  ];

  try {
    const res = await fetch(
      `${API_BASE}/v1/papers/sitemap/entries?limit=5000`,
      {
        next: { revalidate: 3600 },
      },
    );

    if (!res.ok) return staticRoutes;

    const data: { entries: SitemapEntry[] } = await res.json();

    const paperRoutes: MetadataRoute.Sitemap = data.entries.map((e) => ({
      url: `${SITE_URL}/paper/${e.arxiv_id}`,
      lastModified: new Date(e.updated_at),
      changeFrequency: "monthly" as const,
      // Papers decodificados têm conteúdo original — prioridade maior
      priority: e.is_decoded ? 0.8 : 0.3,
    }));

    return [...staticRoutes, ...paperRoutes];
  } catch {
    return staticRoutes;
  }
}
