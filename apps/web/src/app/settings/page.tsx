"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "@/lib/use-api";

interface DigestPrefs {
  enabled: boolean;
  max_papers: number;
  include_general: boolean;
}

export default function SettingsPage() {
  const { authedFetch } = useApi();
  const queryClient = useQueryClient();

  const { data: prefs, isLoading } = useQuery({
    queryKey: ["digest-prefs"],
    queryFn: () => authedFetch<DigestPrefs>("/v1/me/digest/preferences"),
  });

  const update = useMutation({
    mutationFn: (patch: Partial<DigestPrefs>) =>
      authedFetch<DigestPrefs>("/v1/me/digest/preferences", {
        method: "PATCH",
        body: JSON.stringify(patch),
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(["digest-prefs"], result);
    },
  });

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-serif text-4xl leading-tight tracking-tight">
        Settings
      </h1>

      <section className="mt-12 border-t border-border pt-8">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Weekly digest
        </h2>

        {isLoading && (
          <div className="mt-4 h-20 animate-pulse bg-muted/40" />
        )}

        {prefs && (
          <div className="mt-5 space-y-6">
            <div className="flex items-start justify-between gap-6">
              <div>
                <p className="text-[15px]">Send me the weekly digest</p>
                <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                  Papers from the topics, authors, and institutions you follow.
                  Tuesdays.
                </p>
              </div>
              <button
                type="button"
                onClick={() => update.mutate({ enabled: !prefs.enabled })}
                disabled={update.isPending}
                className={`shrink-0 border px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] transition-colors disabled:opacity-50 ${
                  prefs.enabled
                    ? "border-accent bg-accent text-accent-foreground"
                    : "border-border text-muted-foreground hover:border-accent hover:text-accent"
                }`}
              >
                {prefs.enabled ? "On" : "Off"}
              </button>
            </div>

            <div className="flex items-start justify-between gap-6 border-t border-border pt-6">
              <div>
                <p className="text-[15px]">Papers per email</p>
                <p className="mt-1 text-[13px] text-muted-foreground">
                  Fewer means a higher bar for each one.
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                {[4, 6, 8, 10].map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => update.mutate({ max_papers: n })}
                    disabled={update.isPending}
                    className={`tnum border px-3 py-1.5 font-mono text-[11px] transition-colors disabled:opacity-50 ${
                      prefs.max_papers === n
                        ? "border-accent text-accent"
                        : "border-border text-muted-foreground hover:border-accent"
                    }`}
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-start justify-between gap-6 border-t border-border pt-6">
              <div>
                <p className="text-[15px]">Fill with general feed</p>
                <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                  When you follow nothing, or nothing matched, send the
                  highest-priority papers instead of nothing.
                </p>
              </div>
              <button
                type="button"
                onClick={() =>
                  update.mutate({ include_general: !prefs.include_general })
                }
                disabled={update.isPending}
                className={`shrink-0 border px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] transition-colors disabled:opacity-50 ${
                  prefs.include_general
                    ? "border-accent bg-accent text-accent-foreground"
                    : "border-border text-muted-foreground hover:border-accent hover:text-accent"
                }`}
              >
                {prefs.include_general ? "On" : "Off"}
              </button>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}