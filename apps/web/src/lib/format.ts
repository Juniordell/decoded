export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);

  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`;

  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: diffSec > 31536000 ? "numeric" : undefined,
  });
}

export function compactNumber(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

/** Mapeia códigos arXiv para rótulos legíveis. */
export const CATEGORY_LABELS: Record<string, string> = {
  "cs.AI": "Artificial Intelligence",
  "cs.CL": "Computation & Language",
  "cs.LG": "Machine Learning",
  "cs.CV": "Computer Vision",
  "cs.NE": "Neural & Evolutionary",
  "cs.RO": "Robotics",
  "cs.IR": "Information Retrieval",
  "stat.ML": "Statistics — ML",
};

export function categoryLabel(code: string): string {
  return CATEGORY_LABELS[code] ?? code;
}

export function categoryShort(code: string): string {
  return code.replace(/^(cs|stat|math|eess)\./, "");
}