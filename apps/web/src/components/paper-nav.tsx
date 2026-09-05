"use client";

import { useEffect, useState } from "react";

export interface NavItem {
  id: string;
  label: string;
}

export function PaperNav({ items }: { items: NavItem[] }) {
  const [active, setActive] = useState<string | null>(items[0]?.id ?? null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-80px 0px -60% 0px" },
    );

    for (const item of items) {
      const el = document.getElementById(item.id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, [items]);

  useEffect(() => {
    function onScroll() {
      const total = document.body.scrollHeight - window.innerHeight;
      setProgress(total > 0 ? Math.min(window.scrollY / total, 1) : 0);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav className="hidden lg:block">
      <div className="border-b border-rule-strong pb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-subtle">
        On this page
      </div>

      <ul className="flex flex-col gap-[11px] border-b border-border py-4">
        {items.map((item) => {
          const cls =
            active === item.id
              ? "text-accent"
              : "text-muted-foreground hover:text-foreground";
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                aria-current={active === item.id ? "true" : undefined}
                className={`block font-mono text-[12px] transition-colors ${cls}`}
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>

      {/* Progresso de leitura: um fio, não uma barra */}
      <div
        className="mt-4 h-px w-full bg-border"
        role="presentation"
        aria-hidden="true"
      >
        <div
          className="h-px bg-accent transition-all duration-150"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      <p className="mt-[18px] font-mono text-[11.5px] leading-[1.75] text-subtle">
        Every layer here is generated from the paper itself. The PDF is one
        click away.
      </p>
    </nav>
  );
}
