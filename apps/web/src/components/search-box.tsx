"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { EVENTS, capture } from "@/lib/analytics";

const EXAMPLES = [
  "how do models learn from fewer examples",
  "robots that imitate human motion",
  "why benchmarks overstate reasoning ability",
  "cutting inference cost without losing accuracy",
];

export function SearchBox({ autoFocus = false }: { autoFocus?: boolean }) {
  const router = useRouter();
  const params = useSearchParams();
  const [value, setValue] = useState(params.get("q") ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  function submit(query: string) {
    const trimmed = query.trim();
    if (trimmed.length < 2) return;
    capture(EVENTS.SEARCH_PERFORMED, {
      query_length: trimmed.length,
      from_example: EXAMPLES.includes(trimmed),
    });
    router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <div>
      <div className="flex items-center gap-3 border-b border-border pb-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Ask
        </span>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit(value);
          }}
          placeholder="what are you trying to understand?"
          className="flex-1 bg-transparent text-[17px] outline-none placeholder:text-muted-foreground/50"
        />
        {value.length >= 2 && (
          <button
            type="button"
            onClick={() => submit(value)}
            className="font-mono text-[11px] uppercase tracking-[0.16em] text-accent transition-opacity hover:opacity-70"
          >
            Search
          </button>
        )}
      </div>

      {!params.get("q") && (
        <div className="mt-5">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground/60">
            Try
          </p>
          <ul className="mt-2.5 space-y-1.5">
            {EXAMPLES.map((ex) => (
              <li key={ex}>
                <button
                  type="button"
                  onClick={() => {
                    setValue(ex);
                    submit(ex);
                  }}
                  className="text-left text-[14px] text-muted-foreground transition-colors hover:text-accent"
                >
                  {ex}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
