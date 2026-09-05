import type {
  Analogies,
  DeepDive,
  FiguresExplained,
  OneSentence,
  SixtySecondRead,
  VocabTerm,
  Vocabulary,
} from "@/lib/decoded-types";
import { DEEP_DIVE_ORDER } from "@/lib/decoded-types";
import { Resolve } from "./brand";
import { VocabText } from "./vocab-text";

/* ---------------------------------------------------------------- */
/* Wrapper comum                                                      */
/* ---------------------------------------------------------------- */

/**
 * Cada camada do decode é aberta pela régua "The Resolve" — fragmentos que
 * viram linha contínua — e por um rótulo em mono. Sem cards, sem elevação.
 */
export function Section({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-28">
      <Resolve className="mb-8 mt-[34px]" />
      <h2 className="mb-3.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
        {label}
      </h2>
      {children}
    </section>
  );
}

/* ---------------------------------------------------------------- */
/* One sentence — o destaque                                          */
/* ---------------------------------------------------------------- */
export function OneSentenceBlock({ data }: { data: OneSentence }) {
  return (
    <p className="max-w-[56ch] font-serif text-[clamp(21px,2.3vw,25px)] leading-[1.5] [text-wrap:pretty]">
      {data.text}
    </p>
  );
}

/* ---------------------------------------------------------------- */
/* 60-second read                                                     */
/* ---------------------------------------------------------------- */
const SIXTY_LABELS = [
  { key: "problem", label: "Problem" },
  { key: "approach", label: "Approach" },
  { key: "result", label: "Result" },
] as const;

export function SixtySecondBlock({
  data,
  terms,
}: {
  data: SixtySecondRead;
  terms: VocabTerm[];
}) {
  return (
    <div className="space-y-5">
      {SIXTY_LABELS.map(({ key, label }) => (
        <div key={key} className="grid gap-1.5 sm:grid-cols-[96px_1fr] sm:gap-6">
          <p className="pt-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
            {label}
          </p>
          <p className="max-w-[64ch] leading-[1.6] [text-wrap:pretty]">
            <VocabText text={data[key]} terms={terms} />
          </p>
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* Deep dive                                                          */
/* ---------------------------------------------------------------- */
export function DeepDiveBlock({
  data,
  terms,
}: {
  data: DeepDive;
  terms: VocabTerm[];
}) {
  return (
    <div className="space-y-9">
      {DEEP_DIVE_ORDER.map((key, i) => {
        const section = data[key];
        if (!section?.body) return null;

        return (
          <div key={key}>
            <div className="mb-2.5 flex items-baseline gap-3.5">
              <span className="tnum font-mono text-[11.5px] text-subtle">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="font-serif text-[22px] font-semibold leading-[1.3] tracking-[-0.01em] [text-wrap:pretty]">
                {section.heading}
              </h3>
            </div>
            <p className="max-w-[64ch] leading-[1.6] [text-wrap:pretty] sm:pl-[34px]">
              <VocabText text={section.body} terms={terms} />
            </p>
          </div>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* Figures                                                            */
/* ---------------------------------------------------------------- */
export function FiguresBlock({ data }: { data: FiguresExplained }) {
  if (data.items.length === 0) return null;

  return (
    <div className="space-y-5">
      {data.items.map((fig, i) => (
        <figure key={i} className="bg-surface px-6 py-[22px]">
          <figcaption className="mb-2.5 font-mono text-[12px] tracking-[0.06em] text-accent">
            {fig.figure_ref}
          </figcaption>

          {fig.caption_from_paper && (
            <p className="mb-3.5 max-w-[62ch] font-serif text-[15px] italic leading-[1.55] text-subtle">
              {fig.caption_from_paper}
            </p>
          )}

          <p className="max-w-[62ch] text-[17px] leading-[1.55] [text-wrap:pretty]">
            {fig.plain_language}
          </p>

          <p className="mt-3.5 max-w-[62ch] text-[16px] leading-[1.55] text-muted-foreground [text-wrap:pretty]">
            <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-subtle">
              Takeaway ·{" "}
            </span>
            {fig.key_insight}
          </p>
        </figure>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* Analogies                                                          */
/* ---------------------------------------------------------------- */
export function AnalogiesBlock({ data }: { data: Analogies }) {
  if (data.items.length === 0) return null;

  return (
    <div className="space-y-5">
      {data.items.map((item, i) => (
        <div key={i} className="border-l-2 border-accent bg-tint px-5 py-4">
          <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
            {item.concept}
          </p>
          <p className="max-w-[58ch] text-[16.5px] leading-[1.55] [text-wrap:pretty]">
            {item.analogy}
          </p>
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- */
/* Vocabulary                                                         */
/* ---------------------------------------------------------------- */
export function VocabularyBlock({ data }: { data: Vocabulary }) {
  if (data.terms.length === 0) return null;

  return (
    <dl className="flex flex-col gap-3.5">
      {data.terms.map((t, i) => (
        <div key={i} className="flex flex-wrap gap-x-4 gap-y-1.5">
          <dt className="min-w-[150px] font-mono text-[13px] text-accent">
            {t.term}
          </dt>
          <dd className="flex-[1_1_300px] text-[16px] leading-[1.55] text-muted-foreground">
            {t.definition}
          </dd>
        </div>
      ))}
    </dl>
  );
}
