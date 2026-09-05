import { ImageResponse } from "next/og";

export const runtime = "nodejs";
export const alt = "Decoded — AI research, explained for humans";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const PAPER = "#F7F6F1";
const INK = "#16191A";
const PINE = "#14573C";
const SUBTLE = "#6E7573";

/** The Layer Stack, montado com divs — satori não precisa de SVG para barras. */
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

export default function OgImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        background: PAPER,
        padding: "72px",
        fontFamily: "sans-serif",
        position: "relative",
      }}
    >
      <LayerStack />

      <div
        style={{
          display: "flex",
          fontSize: 20,
          color: SUBTLE,
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          marginBottom: 36,
        }}
      >
        Decoded · AI research, explained
      </div>

      <div
        style={{
          fontSize: 76,
          lineHeight: 1.08,
          color: INK,
          letterSpacing: "-0.03em",
          fontWeight: 700,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <span>Every AI paper,</span>
        <span style={{ color: PINE }}>explained for humans.</span>
      </div>

      <div
        style={{
          display: "flex",
          fontSize: 26,
          lineHeight: 1.4,
          color: SUBTLE,
          marginTop: 40,
          maxWidth: 760,
        }}
      >
        One sentence, a sixty-second read, figures explained, and analogies that
        name where they break. No PhD required.
      </div>
    </div>,
    size,
  );
}
