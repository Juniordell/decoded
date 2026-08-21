import { notFound } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export default async function PaperPage({
  params,
}: {
  params: Promise<{ arxiv_id: string }>;
}) {
  const { arxiv_id } = await params;

  try {
    const paper = await api.getPaper(arxiv_id);

    return (
      <main className="mx-auto max-w-2xl px-6 py-12">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          {paper.arxiv_id}
        </p>
        <h1 className="mt-3 font-serif text-3xl leading-tight tracking-tight">
          {paper.title}
        </h1>
        <p className="mt-6 text-[15px] leading-relaxed text-muted-foreground">
          {paper.abstract}
        </p>
        <p className="mt-10 font-mono text-[11px] uppercase tracking-[0.14em] text-accent">
          Full decoded view — Day 17
        </p>
      </main>
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
}