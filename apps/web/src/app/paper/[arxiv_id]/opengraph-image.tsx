import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Decoded paper";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_BASE = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export default async function OgImage({
  params,
}: {
  params: { arxiv_id: string };
}) {
  let title = "Decoded";
  let oneSentence: string | null = null;
  let categories: string[] = [];

  try {
    const res = await fetch(`${API_BASE}/v1/papers/${params.arxiv_id}`, {
      next: { revalidate: 3600 },
    });
    if (res.ok) {
      const paper = await res.json();
      title = paper.title ?? title;
      oneSentence = paper.decoded?.one_sentence?.text ?? null;
      categories = (paper.categories ?? []).slice(0, 3);
    }
  } catch {
    // usa os defaults
  }

  const truncated = title.length > 110 ? `${title.slice(0, 110)}…` : title;

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: "#0A1628",
        padding: "64px 72px",
        fontFamily: "sans-serif",
      }}
    >
      {/* topo */}
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div
          style={{
            fontSize: 30,
            color: "#F5F1E8",
            letterSpacing: "-0.02em",
            fontWeight: 700,
          }}
        >
          Decoded
        </div>
        <div
          style={{
            fontSize: 15,
            color: "#6B7A94",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          AI research, explained
        </div>
      </div>

      {/* meio */}
      <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
        <div
          style={{
            fontSize: oneSentence ? 46 : 56,
            lineHeight: 1.15,
            color: "#F5F1E8",
            letterSpacing: "-0.025em",
            fontWeight: 600,
          }}
        >
          {truncated}
        </div>

        {oneSentence && (
          <div
            style={{
              fontSize: 26,
              lineHeight: 1.4,
              color: "#C1440E",
            }}
          >
            {oneSentence.length > 130
              ? `${oneSentence.slice(0, 130)}…`
              : oneSentence}
          </div>
        )}
      </div>

      {/* rodapé */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 24,
          fontSize: 17,
          color: "#6B7A94",
          letterSpacing: "0.14em",
          textTransform: "uppercase",
        }}
      >
        <span>arXiv {params.arxiv_id}</span>
        {categories.map((c) => (
          <span key={c}>{c}</span>
        ))}
      </div>
    </div>,
    size,
  );
}
