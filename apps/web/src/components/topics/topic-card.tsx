import Link from "next/link";
import type { TopicCard as TopicCardType } from "@/lib/api";

const LABEL_STYLES: Record<string, string> = {
  rising: "text-accent",
  new: "text-accent",
  cooling: "text-subtle",
  steady: "text-subtle",
  quiet: "text-subtle",
};

function formatMomentum(value: number, label: string): string {
  if (label === "new") return "new";
  if (label === "quiet") return "—";
  const pct = Math.round(value * 100);
  // Sinal de menos tipográfico, não hífen: números alinham em coluna
  return pct > 0 ? `+${pct}%` : `−${Math.abs(pct)}%`;
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
    <div className="row-shift group border-b border-border last:border-b-0">
      <Link href={`/topic/${topic.slug}`} className="block py-6">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <h3 className="font-serif text-[21px] font-semibold leading-[1.3] tracking-[-0.01em] transition-colors [text-wrap:pretty] group-hover:text-accent">
            {topic.name}
          </h3>
          <span
            className={`tnum shrink-0 font-mono text-[13px] font-medium ${
              LABEL_STYLES[topic.momentum_label] ?? "text-subtle"
            }`}
          >
            {formatMomentum(topic.momentum, topic.momentum_label)}
          </span>
        </div>

        {topic.description && (
          <p className="mt-2 max-w-[54ch] text-[16.5px] leading-[1.5] text-muted-foreground [text-wrap:pretty]">
            {topic.description}
          </p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 font-mono text-[11.5px] uppercase tracking-[0.08em] text-subtle">
          <span className="tnum">{topic.paper_count} papers</span>
          {topic.recent_papers > 0 && (
            <span className="tnum">{topic.recent_papers} recent</span>
          )}
          {showKeywords &&
            keywords.slice(0, 4).map((k) => <span key={k}>{k}</span>)}
        </div>
      </Link>
    </div>
  );
}
