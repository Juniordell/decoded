import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-24 text-center">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        404
      </p>
      <h1 className="mt-4 font-serif text-3xl tracking-tight">
        Institution not found
      </h1>
      <p className="mt-3 text-[15px] text-muted-foreground">
        Institutions are re-clustered weekly, so some slugs change.
      </p>
      <Link
        href="/institutions"
        className="mt-8 inline-block font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:underline"
      >
        ← All institutions
      </Link>
    </main>
  );
}
