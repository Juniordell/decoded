import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-[52ch] px-6 py-24 sm:px-10">
      <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
        404
      </p>
      <h1 className="mt-5 font-serif text-[clamp(30px,4vw,40px)] font-semibold leading-[1.1] tracking-[-0.02em]">
        Author not found
      </h1>
      <p className="mt-4 text-[17px] leading-[1.6] text-muted-foreground [text-wrap:pretty]">
        Authors are re-clustered weekly, so some slugs change.
      </p>
      <Link
        href="/authors"
        className="mt-8 inline-block border-b border-accent-light pb-0.5 font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent transition-colors hover:border-accent"
      >
        ← All authors
      </Link>
    </main>
  );
}
