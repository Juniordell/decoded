"use client";

import { useEffect, useRef, useState } from "react";

/** Campo de leitura com botão de copiar. Usado pela URL do feed do podcast. */
export function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Clipboard bloqueado — o texto continua selecionável ao lado
      return;
    }
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <code className="min-w-0 flex-[1_1_280px] overflow-x-auto border border-border bg-background px-3.5 py-3 font-mono text-[13.5px] text-foreground">
        {value}
      </code>
      <button
        type="button"
        onClick={copy}
        className="flex-none border border-accent bg-accent px-5 py-3 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent-foreground transition-colors hover:border-accent-deep hover:bg-accent-deep"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
