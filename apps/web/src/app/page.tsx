import { api } from "@/lib/api";

export default async function Home() {
  let feed;
  let error: string | null = null;

  try {
    feed = await api.getFeed({ limit: 5 });
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro desconhecido";
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-bold">Decoded</h1>
      <p className="mt-2 text-slate-600">AI research, explained for humans.</p>

      {error && (
        <div className="mt-8 rounded border border-red-300 bg-red-50 p-4 text-red-800">
          <strong>API não respondeu:</strong> {error}
          <p className="mt-2 text-sm">
            A API está rodando em {process.env.NEXT_PUBLIC_API_URL}?
          </p>
        </div>
      )}

      {feed && (
        <>
          <p className="mt-8 text-sm text-slate-500">
            {feed.total} papers no banco
          </p>
          <ul className="mt-4 space-y-4">
            {feed.papers.map((p) => (
              <li key={p.arxiv_id} className="rounded border p-4">
                <div className="text-xs text-slate-400">{p.arxiv_id}</div>
                <div className="font-medium">{p.title}</div>
                {p.one_sentence && (
                  <div className="mt-2 text-sm text-slate-600">
                    {p.one_sentence}
                  </div>
                )}
                <div className="mt-2 flex gap-3 text-xs text-slate-400">
                  <span>prio {p.priority_score.toFixed(1)}</span>
                  <span>{p.citation_count} citações</span>
                  {p.is_decoded && (
                    <span className="text-green-600">
                      decodificado ({p.decoded_sections.length} seções)
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
