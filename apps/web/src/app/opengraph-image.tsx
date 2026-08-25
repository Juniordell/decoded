import { ImageResponse } from "next/og";

export const runtime = "nodejs";
export const alt = "Decoded — AI research, explained for humans";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OgImage() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        background: "#0A1628",
        padding: "72px",
        fontFamily: "sans-serif",
      }}
    >
      <div
        style={{
          fontSize: 22,
          color: "#6B7A94",
          letterSpacing: "0.24em",
          textTransform: "uppercase",
          marginBottom: 32,
        }}
      >
        Decoded
      </div>

      <div
        style={{
          fontSize: 76,
          lineHeight: 1.05,
          color: "#F5F1E8",
          letterSpacing: "-0.03em",
          fontWeight: 700,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <span>Every AI paper,</span>
        <span style={{ color: "#C1440E" }}>explained for humans.</span>
      </div>

      <div
        style={{
          fontSize: 26,
          lineHeight: 1.4,
          color: "#C7BFA5",
          marginTop: 36,
          maxWidth: 800,
        }}
      >
        TL;DRs, deep dives, figure explanations, and analogies. No PhD required.
      </div>
    </div>,
    size,
  );
}
