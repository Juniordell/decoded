import type { Metadata } from "next";
import { Instrument_Serif, Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { Providers } from "@/components/providers";

const serif = Instrument_Serif({
  variable: "--font-serif",
  subsets: ["latin"],
  weight: "400",
});

const sans = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Decoded — AI research, explained for humans",
    template: "%s · Decoded",
  },
  description:
    "Every new AI paper, translated into something you can actually read. TL;DRs, deep dives, figure explanations, and analogies.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${serif.variable} ${sans.variable} ${mono.variable} font-sans antialiased`}
      >
        <Providers>
          <div className="min-h-screen">
            <SiteHeader />
            {children}
            <SiteFooter />
          </div>
        </Providers>
      </body>
    </html>
  );
}

function SiteHeader() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-5xl items-baseline justify-between px-6 py-5">
        <Link href="/" className="group">
          <span className="font-serif text-2xl tracking-tight">Decoded</span>
          <span className="ml-3 hidden font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground sm:inline">
            AI research, explained
          </span>
        </Link>

        <nav className="flex items-center gap-6 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          <Link href="/" className="transition-colors hover:text-foreground">
            Feed
          </Link>
          <Link href="/search" className="transition-colors hover:text-foreground">
            Search
          </Link>
        </nav>
      </div>
    </header>
  );
}

function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-border">
      <div className="mx-auto max-w-5xl px-6 py-10">
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          Decoded · Built by Nelson Dell · {new Date().getFullYear()}
        </p>
      </div>
    </footer>
  );
}