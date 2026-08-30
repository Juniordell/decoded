import Link from "next/link";
import type { TopicCard as TopicCardType } from "@/lib/api";

const LABEL_STYLES: Record<string, string> = {
  rising: "text-accent",
  cooling: "text-muted-foreground/60",
  new: "text-accent",
  steady: "text-muted-foreground/60",
  quiet: "text-muted-foreground/40",
};

function formatMomentum(value: number, label: string): string {
  if (label === "new") return "new";
  if (label === "quiet") return "—";
  const pct = Math.round(value * 100);
  return pct > 0 ? `+${pct}%` : `${pct}%`;
}

export function TopicCard({
  topic,
  showKeywords = true,
}: {
  topic: TopicCardType;
  showKeywords?: boolean;
}) {
  const keywords = topic.keywords ?? [];

  return (
    <Link
      href={`/topic/${topic.slug}`}
      className="group block border-b border-border py-5 last:border-b-0"
    >
      <div className="flex items-baseline justify-between gap-4">
        <h3 className="font-serif text-lg leading-snug tracking-tight transition-colors group-hover:text-accent">
          {topic.name}
        </h3>
        <span
          className={`tnum shrink-0 font-mono text-[11px] uppercase tracking-[0.14em] ${
            LABEL_STYLES[topic.momentum_label] ?? "text-muted-foreground/60"
          }`}
        >
          {formatMomentum(topic.momentum, topic.momentum_label)}
        </span>
      </div>

      {topic.description && (
        <p className="mt-1.5 text-[14px] leading-relaxed text-muted-foreground">
          {topic.description}
        </p>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
        <span className="tnum">{topic.paper_count} papers</span>
        {topic.recent_papers > 0 && (
          <span className="tnum">{topic.recent_papers} recent</span>
        )}
        {showKeywords &&
          keywords.slice(0, 4).map((k) => (
            <span key={k} className="text-muted-foreground/50">
              {k}
            </span>
          ))}
      </div>
    </Link>
  );
}
