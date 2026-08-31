"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(
  /\/+$/,
  "",
);

/**
 * Hook que devolve um fetcher autenticado.
 * Injeta o JWT do Clerk no header Authorization.
 */
export function useApi() {
  const { getToken, isSignedIn } = useAuth();

  const authedFetch = useCallback(
    async <T>(path: string, init?: RequestInit): Promise<T> => {
      const token = await getToken();

      const res = await fetch(`${API_BASE}${path}`, {
        ...init,
        signal: AbortSignal.timeout(30_000),
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...init?.headers,
        },
      });

      if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
      }

      if (res.status === 204) return undefined as T;
      return res.json() as Promise<T>;
    },
    [getToken],
  );

  return { authedFetch, isSignedIn };
}
