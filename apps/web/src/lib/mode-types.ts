/**
 * Tipos dos cinco modos de explicação.
 * Espelham os schemas Pydantic em modes/schemas.py.
 */

export type ModeName = "math" | "analogy" | "story" | "diagram" | "code";

export const ALL_MODES: ModeName[] = [
  "math",
  "analogy",
  "story",
  "diagram",
  "code",
];

export const MODE_LABELS: Record<ModeName, string> = {
  math: "Math",
  analogy: "Analogy",
  story: "Story",
  diagram: "Diagram",
  code: "Code",
};

export const MODE_DESCRIPTIONS: Record<ModeName, string> = {
  math: "The equations, with every symbol explained",
  analogy: "Everyday comparisons, and where they break",
  story: "How the field got here, chronologically",
  diagram: "The method as a flowchart",
  code: "The core algorithm, runnable",
};

/* ---------- math ---------- */
export interface EquationExplained {
  latex: string;
  label: string;
  plain_reading: string;
  what_each_symbol_means: string[];
  why_it_matters: string;
}

export interface MathMode {
  intuition: string;
  equations: EquationExplained[];
  the_trick: string | null;
}

/* ---------- analogy ---------- */
export interface RichAnalogy {
  concept: string;
  domain: string;
  setup: string;
  mapping: string[];
  where_it_breaks: string;
}

export interface AnalogyMode {
  analogies: RichAnalogy[];
}

/* ---------- story ---------- */
export interface StoryBeat {
  year: string | null;
  heading: string;
  body: string;
}

export interface StoryMode {
  beats: StoryBeat[];
  where_it_leaves_us: string;
}

/* ---------- diagram ---------- */
export interface DiagramMode {
  mermaid: string;
  diagram_type: "flowchart" | "sequence" | "state" | "class";
  caption: string;
  walkthrough: string[];
}

/* ---------- code ---------- */
export interface CodeMode {
  language: string;
  code: string;
  what_it_does: string;
  example_usage: string | null;
  caveats: string[];
}

/* ---------- API ---------- */
export type ModeStatus =
  | "pending"
  | "generating"
  | "ready"
  | "failed"
  | "not_applicable";

export interface ModeInfo {
  mode: ModeName;
  status: ModeStatus;
  cached: boolean;
  content: unknown | null;
  generated_at: string | null;
}

export interface ModesListResponse {
  arxiv_id: string;
  modes: ModeInfo[];
  credits_remaining: number | null;
  plan: string | null;
}
