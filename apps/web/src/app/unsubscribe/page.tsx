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
      <p className="font-mono text-[11.5px] uppercase tracking-[0.16em] text-subtle">
        Unsubscribing…
      </p>
    );
  }

  if (state === "error") {
    return (
      <>
        <h1 className="font-serif text-[clamp(30px,4vw,40px)] font-semibold leading-[1.1] tracking-[-0.02em]">
          That link didn&apos;t work
        </h1>
        <p className="mt-5 text-[17px] leading-[1.6] text-muted-foreground [text-wrap:pretty]">
          The link may be malformed or already used. You can turn the digest off
          from your settings.
        </p>
        <Link
          href="/settings"
          className="mt-8 inline-block border-b border-accent-light pb-0.5 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
        >
          Settings →
        </Link>
      </>
    );
  }

  return (
    <>
      <h1 className="font-serif text-[clamp(30px,4vw,40px)] font-semibold leading-[1.1] tracking-[-0.02em]">
        Unsubscribed
      </h1>
      <p className="mt-5 text-[17px] leading-[1.6] text-muted-foreground [text-wrap:pretty]">
        {email ? (
          <>
            No more weekly digests to <span className="font-mono">{email}</span>.
          </>
        ) : (
          "No more weekly digests."
        )}{" "}
        Nothing else changes — your saved papers and account stay as they were.
      </p>
      <div className="mt-8 flex flex-wrap gap-6 font-mono text-[11.5px] uppercase tracking-[0.14em]">
        <Link
          href="/settings"
          className="border-b border-accent-light pb-0.5 text-accent transition-colors hover:border-accent"
        >
          Turn it back on
        </Link>
        <Link
          href="/"
          className="text-subtle transition-colors hover:text-foreground"
        >
          Back to Decoded
        </Link>
      </div>
    </>
  );
}

export default function UnsubscribePage() {
  return (
    <main className="mx-auto max-w-[52ch] px-6 py-24 sm:px-10">
      <Suspense
        fallback={
          <p className="font-mono text-[11.5px] uppercase tracking-[0.16em] text-subtle">
            Loading…
          </p>
        }
      >
        <UnsubscribeInner />
      </Suspense>
    </main>
  );
}