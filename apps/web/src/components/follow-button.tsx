"use client";

import { SignInButton, useAuth } from "@clerk/nextjs";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useApi } from "@/lib/use-api";

interface FollowState {
  target_type: string;
  slug: string;
  following: boolean;
}

export function FollowButton({
  targetType,
  slug,
  initialFollowing = false,
}: {
  targetType: "author" | "institution" | "topic";
  slug: string;
  initialFollowing?: boolean;
}) {
  const { isSignedIn } = useAuth();
  const { authedFetch } = useApi();
  const queryClient = useQueryClient();
  const [following, setFollowing] = useState(initialFollowing);

  const toggle = useMutation({
    mutationFn: () =>
      authedFetch<FollowState>("/v1/follows", {
        method: "POST",
        body: JSON.stringify({ target_type: targetType, slug }),
      }),
    onSuccess: (result) => {
      setFollowing(result.following);
      void queryClient.invalidateQueries({ queryKey: ["follows"] });
    },
  });

  if (!isSignedIn) {
    return (
      <SignInButton mode="modal">
        <button
          type="button"
          className="border border-border px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:border-accent hover:text-accent"
        >
          Follow
        </button>
      </SignInButton>
    );
  }

  return (
    <button
      type="button"
      onClick={() => toggle.mutate()}
      disabled={toggle.isPending}
      className={`border px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] transition-colors disabled:opacity-50 ${
        following
          ? "border-accent bg-accent text-accent-foreground"
          : "border-border text-muted-foreground hover:border-accent hover:text-accent"
      }`}
    >
      {toggle.isPending ? "…" : following ? "Following" : "Follow"}
    </button>
  );
}
