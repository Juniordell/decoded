"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(/\/+$/, "");

function UnsubscribeInner() {
  const params = useSearchParams();
  const token = params.get("token");

  const [state, setState] = useState<"loading" | "done" | "error">("loading");
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setState("error");
      return;
    }

    fetch(`${API_BASE}/v1/me/digest/unsubscribe?token=${encodeURIComponent(token)}`, {
      method: "POST",
    })
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((data: { email: string | null }) => {
        setEmail(data.email);
        setState("done");
      })
      .catch(() => setState("error"));
  }, [token]);

  if (state === "loading") {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        Unsubscribing…
      </p>
    );
  }

  if (state === "error") {
    return (
      <>
        <h1 className="font-serif text-3xl tracking-tight">
          That link didn&apos;t work
        </h1>
        <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
          The link may be malformed or already used. You can turn the digest off
          from your settings.
        </p>
        <Link
          href="/settings"
          className="mt-8 inline-block font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:underline"
        >
          Settings →
        </Link>
      </>
    );
  }

  return (
    <>
      <h1 className="font-serif text-3xl tracking-tight">Unsubscribed</h1>
      <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">
        {email ? (
          <>
            No more weekly digests to <span className="font-mono">{email}</span>.
          </>
        ) : (
          "No more weekly digests."
        )}{" "}
        Nothing else changes — your saved papers and account stay as they were.
      </p>
      <div className="mt-8 flex gap-6 font-mono text-[10px] uppercase tracking-[0.16em]">
        <Link href="/settings" className="text-accent hover:underline">
          Turn it back on
        </Link>
        <Link href="/" className="text-muted-foreground hover:text-foreground">
          Back to Decoded
        </Link>
      </div>
    </>
  );
}

export default function UnsubscribePage() {
  return (
    <main className="mx-auto max-w-lg px-6 py-24">
      <Suspense
        fallback={
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Loading…
          </p>
        }
      >
        <UnsubscribeInner />
      </Suspense>
    </main>
  );
}