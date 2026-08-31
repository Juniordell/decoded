/**
 * Tipos das seções decodificadas.
 *
 * A API devolve `decoded` como um mapa genérico porque cada seção tem shape
 * diferente. Estes tipos espelham os schemas Pydantic em decoding/schemas.py.
 */

export interface OneSentence {
  text: string;
}

export interface SixtySecondRead {
  problem: string;
  approach: string;
  result: string;
}

export interface DeepDiveSection {
  heading: string;
  body: string;
}

export interface DeepDive {
  setup: DeepDiveSection;
  idea: DeepDiveSection;
  method: DeepDiveSection;
  results: DeepDiveSection;
  implications: DeepDiveSection;
}

export interface VocabTerm {
  term: string;
  definition: string;
}

export interface Vocabulary {
  terms: VocabTerm[];
}

export interface Analogy {
  concept: string;
  analogy: string;
}

export interface Analogies {
  items: Analogy[];
}

export interface FigureExplained {
  figure_ref: string;
  caption_from_paper: string | null;
  plain_language: string;
  key_insight: string;
}

export interface FiguresExplained {
  items: FigureExplained[];
}

export type DecodedMap = Record<string, unknown>;

/** Acessores tipados — retornam undefined se a seção não existir. */
export const decoded = {
  oneSentence: (d: DecodedMap) => d.one_sentence as OneSentence | undefined,
  sixtySecond: (d: DecodedMap) => d.sixty_second as SixtySecondRead | undefined,
  deepDive: (d: DecodedMap) => d.deep_dive as DeepDive | undefined,
  vocabulary: (d: DecodedMap) => d.vocabulary as Vocabulary | undefined,
  analogies: (d: DecodedMap) => d.analogies as Analogies | undefined,
  figures: (d: DecodedMap) => d.figures as FiguresExplained | undefined,
};

export const DEEP_DIVE_ORDER = [
  "setup",
  "idea",
  "method",
  "results",
  "implications",
] as const;
