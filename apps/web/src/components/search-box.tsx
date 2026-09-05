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
      <div className="flex items-baseline gap-4 border-b border-rule-strong pb-3">
        <label
          htmlFor="ask"
          className="flex-none font-mono text-[11.5px] uppercase tracking-[0.16em] text-accent"
        >
          Ask
        </label>
        <input
          id="ask"
          ref={inputRef}
          type="search"
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit(value);
          }}
          placeholder="what are you trying to understand?"
          className="min-w-0 flex-1 bg-transparent font-serif text-[clamp(20px,2.4vw,26px)] leading-[1.35] outline-none"
        />
        {value.length >= 2 && (
          <button
            type="button"
            onClick={() => submit(value)}
            className="flex-none border-b border-accent-light pb-0.5 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
          >
            Search
          </button>
        )}
      </div>

      {!params.get("q") && (
        <div className="mt-[clamp(32px,4vw,44px)]">
          <p className="mb-5 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
            Try
          </p>
          <div className="flex flex-col">
            {EXAMPLES.map((ex, i) => (
              <button
                key={ex}
                type="button"
                onClick={() => {
                  setValue(ex);
                  submit(ex);
                }}
                className="row-shift flex w-full items-baseline gap-[18px] border-t border-border py-[18px] text-left last:border-b"
              >
                <span className="tnum flex-none font-mono text-[11.5px] text-subtle">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="font-serif text-[20px] leading-[1.4]">
                  {ex}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
