"use client";

import { SignInButton, useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { EVENTS, capture } from "@/lib/analytics";
import { useApi } from "@/lib/use-api";
import {
  ALL_MODES,
  MODE_DESCRIPTIONS,
  MODE_LABELS,
  type AnalogyMode,
  type CodeMode,
  type DiagramMode,
  type MathMode,
  type ModeInfo,
  type ModeName,
  type ModesListResponse,
  type StoryMode,
} from "@/lib/mode-types";
import { Resolve } from "@/components/brand";
import { DiagramModeView } from "./diagram-mode";
import { MathModeView } from "./math-mode";
import { AnalogyModeView, CodeModeView, StoryModeView } from "./other-modes";
import { useEffect, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(
  /\/+$/,
  "",
);

export function ModeSwitcher({ arxivId }: { arxivId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { isSignedIn } = useAuth();
  const { authedFetch } = useApi();
  const queryClient = useQueryClient();

  const activeMode = (params.get("mode") as ModeName | null) ?? null;

  const { data, isLoading } = useQuery({
    queryKey: ["modes", arxivId],
    queryFn: async (): Promise<ModesListResponse> => {
      if (isSignedIn) {
        return authedFetch<ModesListResponse>(`/v1/papers/${arxivId}/modes`);
      }
      const res = await fetch(`${API_BASE}/v1/papers/${arxivId}/modes`);
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
  });

  const generate = useMutation({
    mutationFn: (mode: ModeName) => {
      capture(EVENTS.MODE_GENERATE_CLICKED, { mode, arxiv_id: arxivId });
      return authedFetch<{
        mode: string;
        status: string;
        content: unknown;
        credits_remaining: number;
        poll_after_ms: number | null;
      }>(`/v1/papers/${arxivId}/modes/${mode}/generate`, {
        method: "POST",
      });
    },
    onSuccess: (result) => {
      capture(EVENTS.MODE_GENERATED, {
        mode: result.mode,
        arxiv_id: arxivId,
        cached: result.status === "ready",
        credits_left: result.credits_remaining,
      });
      void queryClient.invalidateQueries({ queryKey: ["me"] });

      if (result.status === "ready") {
        void queryClient.invalidateQueries({ queryKey: ["modes", arxivId] });
        return;
      }

      if (result.status === "generating") {
        setPolling(result.mode as ModeName);
      }
    },
    onError: (error, mode) => {
      if (error instanceof Error && error.message.includes("402")) {
        capture(EVENTS.MODE_OUT_OF_CREDITS, { mode, arxiv_id: arxivId });
      }
    },
  });

  const [polling, setPolling] = useState<ModeName | null>(null);

  const { data: polled } = useQuery({
    queryKey: ["mode-poll", arxivId, polling],
    queryFn: async (): Promise<ModeInfo> => {
      const res = await fetch(
        `${API_BASE}/v1/papers/${arxivId}/modes/${polling}`,
      );
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: polling !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "generating" || status === "pending" ? 3000 : false;
    },
  });

  useEffect(() => {
    if (!polled) return;
    if (
      polled.status === "ready" ||
      polled.status === "failed" ||
      polled.status === "not_applicable"
    ) {
      setPolling(null);
      void queryClient.invalidateQueries({ queryKey: ["modes", arxivId] });
    }
  }, [polled, arxivId, queryClient]);

  function selectMode(mode: ModeName | null) {
    if (mode) {
      const info = modeMap.get(mode);
      capture(EVENTS.MODE_TAB_CLICKED, {
        mode,
        arxiv_id: arxivId,
        was_cached: info?.status === "ready",
      });
    }
    const next = new URLSearchParams(params.toString());
    if (mode === null) next.delete("mode");
    else next.set("mode", mode);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  if (isLoading) {
    return <div className="mt-[34px] h-10 animate-pulse bg-surface" />;
  }

  const modeMap = new Map<string, ModeInfo>(
    (data?.modes ?? []).map((m) => [m.mode, m]),
  );
  const active = activeMode ? modeMap.get(activeMode) : null;

  return (
    <section id="modes" className="scroll-mt-28">
      <Resolve className="mb-8 mt-[34px]" />

      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
          Explain it different
        </h2>
        <span className="font-mono text-[11.5px] text-subtle">
          the same mechanism, five ways
        </span>
      </div>

      {/* Tabs */}
      <div
        role="tablist"
        className="mb-[30px] mt-[18px] flex flex-wrap items-baseline gap-x-[26px] gap-y-2 border-b border-border"
      >
        {ALL_MODES.map((mode) => {
          const info = modeMap.get(mode);
          const isActive = activeMode === mode;
          const ready = info?.status === "ready";

          return (
            <button
              key={mode}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => selectMode(isActive ? null : mode)}
              className={`-mb-px border-b-2 pb-3 font-mono text-[12px] uppercase tracking-[0.14em] transition-colors ${
                isActive
                  ? "border-accent text-accent"
                  : "border-transparent text-subtle hover:text-foreground"
              }`}
            >
              {MODE_LABELS[mode]}
              {ready && !isActive && (
                <span className="ml-1.5 text-accent-light">·</span>
              )}
            </button>
          );
        })}

        {data?.credits_remaining !== null &&
          data?.credits_remaining !== undefined && (
            <span className="tnum ml-auto pb-3 font-mono text-[11px] uppercase tracking-[0.14em] text-subtle">
              {data.plan === "pro"
                ? "unlimited"
                : `${data.credits_remaining} credits`}
            </span>
          )}
      </div>

      {/* Conteúdo */}
      {activeMode && (
        <div>
          <ModePanel
            mode={activeMode}
            info={active ?? null}
            isSignedIn={!!isSignedIn}
            isGenerating={generate.isPending || polling === activeMode}
            error={generate.error}
            onGenerate={() => generate.mutate(activeMode)}
          />
        </div>
      )}
    </section>
  );
}

function ModePanel({
  mode,
  info,
  isSignedIn,
  isGenerating,
  error,
  onGenerate,
}: {
  mode: ModeName;
  info: ModeInfo | null;
  isSignedIn: boolean;
  isGenerating: boolean;
  error: unknown;
  onGenerate: () => void;
}) {
  // Pronto — renderiza
  if (info?.status === "ready" && info.content) {
    switch (mode) {
      case "math":
        return <MathModeView data={info.content as MathMode} />;
      case "analogy":
        return <AnalogyModeView data={info.content as AnalogyMode} />;
      case "story":
        return <StoryModeView data={info.content as StoryMode} />;
      case "diagram":
        return <DiagramModeView data={info.content as DiagramMode} />;
      case "code":
        return <CodeModeView data={info.content as CodeMode} />;
    }
  }

  if (info?.status === "not_applicable") {
    return (
      <p className="bg-surface px-6 py-5 text-[16px] text-muted-foreground">
        This mode doesn&apos;t fit this paper.
      </p>
    );
  }

  if (isGenerating) {
    return (
      <div className="bg-surface px-8 py-9 text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
          Generating
        </p>
        <p className="mt-2.5 text-[16px] text-muted-foreground">
          This takes 20 to 60 seconds.
        </p>
        <div className="mx-auto mt-6 h-px w-32 overflow-hidden bg-border">
          <div className="h-px w-1/3 animate-[slide_1.4s_ease-in-out_infinite] bg-accent" />
        </div>
      </div>
    );
  }

  // Não gerado
  return (
    <div className="bg-surface px-8 py-9 text-center">
      <p className="font-serif text-[22px] font-semibold tracking-[-0.01em]">
        {MODE_LABELS[mode]}
      </p>
      <p className="mx-auto mt-2.5 max-w-[46ch] text-[16px] leading-[1.55] text-muted-foreground [text-wrap:pretty]">
        {MODE_DESCRIPTIONS[mode]}
      </p>

      {error != null && (
        <p className="mt-4 font-mono text-[11.5px] text-destructive">
          {error instanceof Error && error.message.includes("402")
            ? "Out of credits. They reset weekly."
            : "Generation failed. Try again."}
        </p>
      )}

      <div className="mt-7">
        {isSignedIn ? (
          <button
            type="button"
            onClick={onGenerate}
            className="border border-accent bg-accent px-5 py-3 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent-foreground transition-colors hover:bg-accent-deep hover:border-accent-deep"
          >
            Generate · 1 credit
          </button>
        ) : (
          <SignInButton mode="modal">
            <button
              type="button"
              className="border border-accent bg-accent px-5 py-3 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent-foreground transition-colors hover:bg-accent-deep hover:border-accent-deep"
            >
              Sign in to generate
            </button>
          </SignInButton>
        )}
      </div>
    </div>
  );
}
