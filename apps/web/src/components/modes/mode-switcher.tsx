"use client";

import { SignInButton, useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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
import { DiagramModeView } from "./diagram-mode";
import { MathModeView } from "./math-mode";
import { AnalogyModeView, CodeModeView, StoryModeView } from "./other-modes";

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
    mutationFn: (mode: ModeName) =>
      authedFetch<{
        mode: string;
        status: string;
        content: unknown;
        credits_remaining: number;
      }>(`/v1/papers/${arxivId}/modes/${mode}/generate`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["modes", arxivId] });
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  function selectMode(mode: ModeName | null) {
    const next = new URLSearchParams(params.toString());
    if (mode === null) next.delete("mode");
    else next.set("mode", mode);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  if (isLoading) {
    return (
      <div className="h-10 animate-pulse border-t border-border bg-muted/30" />
    );
  }

  const modeMap = new Map<string, ModeInfo>(
    (data?.modes ?? []).map((m) => [m.mode, m]),
  );
  const active = activeMode ? modeMap.get(activeMode) : null;

  return (
    <section id="modes" className="scroll-mt-24 border-t border-border pt-8">
      <h2 className="mb-1 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        Explain it different
      </h2>
      <p className="mb-5 text-[14px] text-muted-foreground">
        Same paper, five ways to understand it.
      </p>

      {/* Tabs */}
      <div className="flex flex-wrap gap-x-5 gap-y-2 border-b border-border pb-3">
        {ALL_MODES.map((mode) => {
          const info = modeMap.get(mode);
          const isActive = activeMode === mode;
          const ready = info?.status === "ready";

          return (
            <button
              key={mode}
              type="button"
              onClick={() => selectMode(isActive ? null : mode)}
              className={`font-mono text-[11px] uppercase tracking-[0.14em] transition-colors ${
                isActive
                  ? "text-accent"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {MODE_LABELS[mode]}
              {ready && <span className="ml-1 text-accent/60">·</span>}
            </button>
          );
        })}

        {data?.credits_remaining !== null &&
          data?.credits_remaining !== undefined && (
            <span className="ml-auto tnum font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/60">
              {data.plan === "pro"
                ? "unlimited"
                : `${data.credits_remaining} credits`}
            </span>
          )}
      </div>

      {/* Conteúdo */}
      {activeMode && (
        <div className="mt-8">
          <ModePanel
            mode={activeMode}
            info={active ?? null}
            isSignedIn={!!isSignedIn}
            isGenerating={generate.isPending}
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
      <p className="border border-border bg-secondary/40 p-5 text-[14px] text-muted-foreground">
        This mode doesn&apos;t fit this paper.
      </p>
    );
  }

  if (isGenerating) {
    return (
      <div className="border border-border bg-secondary/40 p-8 text-center">
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-accent">
          Generating
        </p>
        <p className="mt-2 text-[14px] text-muted-foreground">
          This takes 20 to 60 seconds.
        </p>
        <div className="mx-auto mt-5 h-px w-32 overflow-hidden bg-border">
          <div className="h-px w-1/3 animate-[slide_1.4s_ease-in-out_infinite] bg-accent" />
        </div>
      </div>
    );
  }

  // Não gerado
  return (
    <div className="border border-border bg-secondary/40 p-8 text-center">
      <p className="font-serif text-xl tracking-tight">{MODE_LABELS[mode]}</p>
      <p className="mx-auto mt-2 max-w-sm text-[14px] leading-relaxed text-muted-foreground">
        {MODE_DESCRIPTIONS[mode]}
      </p>

      {error != null && (
        <p className="mt-4 font-mono text-[11px] text-destructive">
          {error instanceof Error && error.message.includes("402")
            ? "Out of credits. They reset weekly."
            : "Generation failed. Try again."}
        </p>
      )}

      <div className="mt-6">
        {isSignedIn ? (
          <button
            type="button"
            onClick={onGenerate}
            className="border border-accent px-5 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-accent transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            Generate · 1 credit
          </button>
        ) : (
          <SignInButton mode="modal">
            <button
              type="button"
              className="border border-accent px-5 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-accent transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              Sign in to generate
            </button>
          </SignInButton>
        )}
      </div>
    </div>
  );
}
