"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Column,
  PageShell,
  PageTitle,
  Rail,
  RailHeading,
  RailNote,
} from "@/components/page-shell";
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

  const toggleClass = (on: boolean) =>
    `shrink-0 border px-5 py-2.5 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors disabled:opacity-50 ${
      on
        ? "border-accent bg-accent text-accent-foreground"
        : "border-border text-subtle hover:border-accent hover:text-accent"
    }`;

  return (
    <PageShell>
      <Column>
        <PageTitle className="mb-[clamp(32px,4vw,44px)]">Settings</PageTitle>

        <section>
          <h2 className="border-b border-rule-strong pb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
            Weekly digest
          </h2>

          {isLoading && <div className="mt-6 h-24 animate-pulse bg-surface" />}

          {prefs && (
            <div className="mt-6 space-y-7">
              <div className="flex items-start justify-between gap-6">
                <div>
                  <p className="text-[17px]">Send me the weekly digest</p>
                  <p className="mt-1.5 max-w-[52ch] text-[15.5px] leading-[1.55] text-muted-foreground">
                    Papers from the topics, authors, and institutions you follow.
                    Tuesdays.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => update.mutate({ enabled: !prefs.enabled })}
                  disabled={update.isPending}
                  className={toggleClass(prefs.enabled)}
                >
                  {prefs.enabled ? "On" : "Off"}
                </button>
              </div>

              <div className="flex items-start justify-between gap-6 border-t border-border pt-7">
                <div>
                  <p className="text-[17px]">Papers per email</p>
                  <p className="mt-1.5 text-[15.5px] leading-[1.55] text-muted-foreground">
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
                      className={`tnum border px-3.5 py-2.5 font-mono text-[12px] transition-colors disabled:opacity-50 ${
                        prefs.max_papers === n
                          ? "border-accent text-accent"
                          : "border-border text-subtle hover:border-accent"
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-start justify-between gap-6 border-t border-border pt-7">
                <div>
                  <p className="text-[17px]">Fill with general feed</p>
                  <p className="mt-1.5 max-w-[52ch] text-[15.5px] leading-[1.55] text-muted-foreground">
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
                  className={toggleClass(prefs.include_general)}
                >
                  {prefs.include_general ? "On" : "Off"}
                </button>
              </div>
            </div>
          )}
        </section>
      </Column>

      <Rail>
        <RailHeading>What the digest is</RailHeading>
        <RailNote>
          One email, Tuesdays. Paper title, the one-sentence layer, and the
          number that matters. It should read like a page from the site that
          happened to arrive in an inbox.
        </RailNote>
      </Rail>
    </PageShell>
  );
}
