import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * A grade de toda página: coluna de leitura à esquerda, trilho de contexto à
 * direita. O trilho quebra para baixo no mobile e some do fluxo visual sem
 * levar conteúdo junto.
 */
export function PageShell({
  children,
  className,
  tight = false,
}: {
  children: React.ReactNode;
  className?: string;
  tight?: boolean;
}) {
  return (
    <main
      className={cn(
        "mx-auto flex max-w-[1240px] flex-wrap items-start gap-x-[clamp(40px,5vw,72px)] gap-y-14 px-6 pb-[clamp(64px,8vw,104px)] sm:px-10",
        tight
          ? "pt-[clamp(36px,4vw,56px)]"
          : "pt-[clamp(44px,5vw,76px)]",
        className,
      )}
    >
      {children}
    </main>
  );
}

/** Coluna de leitura. Mede no máximo ~70ch onde o texto corre longo. */
export function Column({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "w-full min-w-0 lg:w-auto lg:flex-[1_1_580px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Trilho lateral: metadados, explicação do método, limites. */
export function Rail({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <aside
      className={cn(
        "w-full lg:sticky lg:top-[104px] lg:w-auto lg:min-w-[240px] lg:flex-[0_1_264px]",
        className,
      )}
    >
      {children}
    </aside>
  );
}

/** Cabeça do trilho: rótulo em mono sobre uma régua forte. */
export function RailHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-b border-rule-strong pb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
      {children}
    </div>
  );
}

/** Bloco do trilho, separado por fio de cabelo. */
export function RailBlock({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("border-b border-border py-[18px]", className)}>
      {children}
    </div>
  );
}

/** Nota corrida do trilho — mono pequeno, entrelinha larga. */
export function RailNote({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "mt-[18px] font-mono text-[11.5px] leading-[1.75] text-muted-foreground",
        className,
      )}
    >
      {children}
    </p>
  );
}

/**
 * "Where it breaks" — a coisa que mais constrói confiança é nomear onde a
 * própria explicação para de valer.
 */
export function WhereItBreaks({
  children,
  label = "Where it breaks",
  className,
}: {
  children: React.ReactNode;
  label?: string;
  className?: string;
}) {
  return (
    <div className={cn("border-l-2 border-accent bg-tint px-5 py-4", className)}>
      <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
        {label}
      </div>
      <div className="text-[15.5px] leading-[1.55] text-foreground/90 [text-wrap:pretty]">
        {children}
      </div>
    </div>
  );
}

/** Título de página. Literata, apertado, uma medida curta. */
export function PageTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <h1
      className={cn(
        "font-serif text-[clamp(38px,4.8vw,58px)] font-semibold leading-[1.05] tracking-[-0.028em] [text-wrap:pretty]",
        className,
      )}
    >
      {children}
    </h1>
  );
}

/** Subtítulo/deck sob o título. */
export function PageLead({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "max-w-[56ch] text-[19px] leading-[1.6] text-foreground/80 [text-wrap:pretty]",
        className,
      )}
    >
      {children}
    </p>
  );
}

/** Rótulo de seção em mono — o registro "isto é um dado, não prosa". */
export function SectionLabel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "font-mono text-[11px] uppercase tracking-[0.16em] text-subtle",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Caixa de erro — função de interface, fora da paleta da marca. */
export function ErrorNote({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div className="border-l-2 border-destructive bg-surface px-5 py-4">
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-destructive">
        {title}
      </p>
      <p className="mt-2 text-[15px] text-muted-foreground">{message}</p>
    </div>
  );
}

/** Número que importa: rótulo em mono, valor em Literata com numerais tabulares. */
export function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "accent" | "muted";
}) {
  const toneClass =
    tone === "accent"
      ? "text-accent"
      : tone === "muted"
        ? "text-muted-foreground"
        : "";

  return (
    <div>
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
        {label}
      </p>
      <p
        className={`tnum mt-1.5 font-serif text-[30px] font-bold leading-none tracking-[-0.03em] ${toneClass}`}
      >
        {value}
      </p>
    </div>
  );
}

/** Seção secundária: rótulo em mono sobre fio de cabelo. */
export function SubSection({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-t border-border pt-7", className)}>
      <h2 className="mb-4 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
        {label}
      </h2>
      {children}
    </section>
  );
}

/** Link de volta ao índice de onde a página veio. */
export function BackLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="inline-block border-b border-accent-light pb-0.5 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
    >
      {children}
    </Link>
  );
}
