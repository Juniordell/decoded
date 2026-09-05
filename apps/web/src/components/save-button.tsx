"use client";

import { SignInButton, useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "@/lib/use-api";
import { EVENTS, capture } from "@/lib/analytics";

interface SaveState {
  arxiv_id: string;
  saved: boolean;
}

export function SaveButton({ arxivId }: { arxivId: string }) {
  const { isSignedIn } = useAuth();
  const { authedFetch } = useApi();
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["saved", arxivId],
    queryFn: () => authedFetch<SaveState>(`/v1/me/saved/${arxivId}`),
    enabled: !!isSignedIn,
  });

  const toggle = useMutation({
    mutationFn: () =>
      authedFetch<SaveState>("/v1/me/saved", {
        method: "POST",
        body: JSON.stringify({ arxiv_id: arxivId }),
      }),
    onSuccess: (result) => {
      capture(result.saved ? EVENTS.PAPER_SAVED : EVENTS.PAPER_UNSAVED, {
        arxiv_id: arxivId,
      });
      queryClient.setQueryData(["saved", arxivId], result);
      void queryClient.invalidateQueries({ queryKey: ["library"] });
    },
  });

  if (!isSignedIn) {
    return (
      <SignInButton mode="modal">
        <button
          type="button"
          className="border-b border-accent-light font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
        >
          Save
        </button>
      </SignInButton>
    );
  }

  const saved = data?.saved ?? false;

  return (
    <button
      type="button"
      onClick={() => toggle.mutate()}
      disabled={toggle.isPending}
      className={`border-b font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors disabled:opacity-50 ${
        saved ? "border-accent" : "border-accent-light hover:border-accent"
      }`}
    >
      {toggle.isPending ? "..." : saved ? "Saved" : "Save"}
    </button>
  );
}
