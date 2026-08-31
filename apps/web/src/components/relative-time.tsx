"use client";

import { useEffect, useState } from "react";
import { relativeTime } from "@/lib/format";

/**
 * Tempo relativo sem quebrar hidratação.
 *
 * O servidor renderiza a data absoluta, que é estável e sobrevive ao cache
 * do ISR. Depois da hidratação, troca pelo relativo, que é o que o usuário
 * quer ler. Sem isso, "4d ago" no HTML em cache vira "5d ago" no cliente
 * e o React reclama.
 */
export function RelativeTime({
  iso,
  className,
}: {
  iso: string;
  className?: string;
}) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const absolute = new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  return (
    <span className={className} suppressHydrationWarning>
      {mounted ? relativeTime(iso) : absolute}
    </span>
  );
}