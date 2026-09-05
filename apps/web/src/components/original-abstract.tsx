"use client";

import { useState } from "react";

export function OriginalAbstract({ abstract }: { abstract: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-[clamp(40px,5vw,60px)] border-t border-border pt-[22px]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-opacity hover:opacity-70"
      >
        {open ? "− Original abstract" : "+ Original abstract"}
      </button>

      {open && (
        <p className="mt-[18px] max-w-[74ch] font-mono text-[12.5px] leading-[1.75] text-muted-foreground">
          {abstract}
        </p>
      )}
    </div>
  );
}
