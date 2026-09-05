import Link from "next/link";
import { DecodedLogo, LayerStack } from "@/components/brand";

const LINKS = [
  { href: "/topics", label: "topics" },
  { href: "/authors", label: "authors" },
  { href: "/institutions", label: "institutions" },
  { href: "/feed.xml", label: "rss", external: true },
  { href: "https://arxiv.org", label: "arxiv", external: true },
];

export function SiteFooter() {
  return (
    <footer className="relative mt-24 overflow-hidden bg-[#16191A] px-6 py-11 text-[#F7F6F1] sm:px-10">
      <LayerStack className="pointer-events-none absolute right-[-4%] top-1/2 w-[44%] min-w-[320px] -translate-y-1/2 text-[#63BE93] opacity-[0.08]" />

      <div className="relative mx-auto flex max-w-[1240px] flex-wrap items-center justify-between gap-6">
        <div className="flex flex-col gap-2.5">
          <DecodedLogo width={126} tone="reversed" />
          <span className="font-mono text-[12px] text-[#8A908C]">
            Built by Nelson Dell · {new Date().getFullYear()}
          </span>
        </div>

        <nav className="flex flex-wrap gap-6 font-mono text-[12px]">
          {LINKS.map((link) =>
            link.external ? (
              <a
                key={link.href}
                href={link.href}
                target={link.href.startsWith("http") ? "_blank" : undefined}
                rel="noopener noreferrer"
                className="border-b border-transparent text-[#63BE93] transition-colors hover:border-[#63BE93]"
              >
                {link.label}
              </a>
            ) : (
              <Link
                key={link.href}
                href={link.href}
                className="border-b border-transparent text-[#63BE93] transition-colors hover:border-[#63BE93]"
              >
                {link.label}
              </Link>
            ),
          )}
        </nav>
      </div>
    </footer>
  );
}
