"use client";

import { useState } from "react";

export function OriginalAbstract({ abstract }: { abstract: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-border pt-8">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? "− " : "+ "} Original abstract
      </button>

      {open && (
        <p className="mt-4 text-[14px] leading-relaxed text-muted-foreground">
          {abstract}
        </p>
      )}
    </div>
  );
}
