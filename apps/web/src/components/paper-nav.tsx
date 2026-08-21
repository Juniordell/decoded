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
    <nav className="sticky top-24 hidden lg:block">
      <div className="mb-5 h-px w-full bg-border">
        <div
          className="h-px bg-accent transition-all duration-150"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      <ul className="space-y-2.5">
        {items.map((item) => {
          const cls =
            active === item.id
              ? "text-accent"
              : "text-muted-foreground/60 hover:text-foreground";
          return (
            <li key={item.id}>
              <a
                href={`#${item.id}`}
                className={`block font-mono text-[10px] uppercase tracking-[0.16em] transition-colors ${cls}`}
              >
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
