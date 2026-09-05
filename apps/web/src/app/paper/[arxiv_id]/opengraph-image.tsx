import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Decoded paper";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_BASE = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const PAPER = "#F7F6F1";
const INK = "#16191A";
const PINE = "#14573C";
const PINE_LIGHT = "#63BE93";
const SUBTLE = "#6E7573";

/**
 * O ícone: duas linhas fragmentadas em cima (notação), duas contínuas embaixo
 * (linguagem). Montado com divs porque este cartão é gerado aos milhares.
 */
function Mark() {
  const row = (widths: number[], opacity: number) => (
    <div style={{ display: "flex", gap: 8, opacity }}>
      {widths.map((w, i) => (
        <div key={i} style={{ width: w, height: 6, background: PINE }} />
      ))}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {row([14, 10, 16], 0.45)}
      {row([24, 24], 0.45)}
      {row([56], 1)}
      {row([40], 1)}
    </div>
  );
}

/** O Layer Stack ao fundo, em 8% de Pine. */
function LayerStack() {
  return (
    <div
      style={{
        position: "absolute",
        right: -40,
        top: "50%",
        transform: "translateY(-50%)",
        display: "flex",
        flexDirection: "column",
        gap: 26,
        opacity: 0.08,
      }}
    >
      {[520, 420, 324, 224, 130].map((w) => (
        <div key={w} style={{ width: w, height: 22, background: PINE }} />
      ))}
    </div>
  );
}

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
        background: PAPER,
        padding: "64px 72px",
        fontFamily: "sans-serif",
        position: "relative",
      }}
    >
      <LayerStack />

      {/* topo */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 20,
          position: "relative",
        }}
      >
        <Mark />
        <div
          style={{
            display: "flex",
            fontSize: 30,
            color: INK,
            letterSpacing: "-0.02em",
            fontWeight: 700,
          }}
        >
          Decoded
        </div>
      </div>

      {/* meio */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 28,
          position: "relative",
        }}
      >
        <div
          style={{
            display: "flex",
            fontSize: oneSentence ? 46 : 56,
            lineHeight: 1.15,
            color: INK,
            letterSpacing: "-0.025em",
            fontWeight: 600,
          }}
        >
          {truncated}
        </div>

        {oneSentence && (
          <div
            style={{
              display: "flex",
              fontSize: 26,
              lineHeight: 1.4,
              color: SUBTLE,
              borderBottom: `3px solid ${PINE_LIGHT}`,
              paddingBottom: 14,
              maxWidth: 900,
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
          color: SUBTLE,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          position: "relative",
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
