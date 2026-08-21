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
import { VocabText } from "./vocab-text";

/* ---------------------------------------------------------------- */
/* Wrapper comum                                                      */
/* ---------------------------------------------------------------- */
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
    <section id={id} className="scroll-mt-24 border-t border-border pt-8">
      <h2 className="mb-5 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
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
    <p className="font-serif text-[26px] leading-[1.35] tracking-tight sm:text-3xl">
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
        <div
          key={key}
          className="grid gap-1.5 sm:grid-cols-[88px_1fr] sm:gap-5"
        >
          <p className="pt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
            {label}
          </p>
          <p className="text-[15px] leading-relaxed">
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
    <div className="space-y-8">
      {DEEP_DIVE_ORDER.map((key, i) => {
        const section = data[key];
        if (!section?.body) return null;

        return (
          <div key={key}>
            <div className="mb-2 flex items-baseline gap-3">
              <span className="tnum font-mono text-[10px] text-muted-foreground/50">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="font-serif text-xl leading-snug tracking-tight">
                {section.heading}
              </h3>
            </div>
            <p className="pl-0 text-[15px] leading-relaxed text-foreground/90 sm:pl-8">
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
    <div className="space-y-7">
      {data.items.map((fig, i) => (
        <figure key={i} className="border-l-2 border-accent/30 pl-5">
          <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
            {fig.figure_ref}
          </figcaption>

          {fig.caption_from_paper && (
            <p className="mb-3 border-l border-border pl-3 text-[13px] italic leading-relaxed text-muted-foreground">
              {fig.caption_from_paper}
            </p>
          )}

          <p className="text-[15px] leading-relaxed">{fig.plain_language}</p>

          <p className="mt-3 text-[14px] leading-relaxed text-foreground/70">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
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
    <div className="space-y-6">
      {data.items.map((item, i) => (
        <div key={i} className="bg-secondary/50 p-5">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
            {item.concept}
          </p>
          <p className="mt-2.5 text-[15px] leading-relaxed">{item.analogy}</p>
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
    <dl className="space-y-4">
      {data.terms.map((t, i) => (
        <div key={i} className="grid gap-1 sm:grid-cols-[160px_1fr] sm:gap-5">
          <dt className="font-mono text-[12px] text-accent">{t.term}</dt>
          <dd className="text-[14px] leading-relaxed text-foreground/85">
            {t.definition}
          </dd>
        </div>
      ))}
    </dl>
  );
}
