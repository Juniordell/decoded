import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter, Literata } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { ClerkProvider } from "@clerk/nextjs";
import { PostHogProvider } from "@/components/posthog-provider";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";

// Três faces, três funções, sem sobreposição.
// Literata carrega títulos e o texto que se lê como artigo; o eixo óptico
// deixa a mesma família servir a um título de 56px e a um corpo de 18px.
const serif = Literata({
  variable: "--font-serif",
  subsets: ["latin"],
  style: ["normal", "italic"],
  display: "swap",
});

// Inter só veste a interface: navegação, botões, rótulos de formulário.
const sans = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

// Mono é o sinal de que uma string é dado, não prosa: IDs do arXiv, datas,
// categorias, código, rótulos de seção.
const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Decoded — AI research, explained for humans",
    template: "%s · Decoded",
  },
  description:
    "Every new AI paper from arXiv, translated into something you can actually read. TL;DRs, deep dives, figure explanations, and analogies. No PhD required.",
  keywords: [
    "AI research",
    "machine learning papers",
    "arXiv",
    "paper summaries",
    "LLM research",
    "AI explained",
  ],
  authors: [{ name: "Nelson Dell" }],
  openGraph: {
    type: "website",
    siteName: "Decoded",
    title: "Decoded — AI research, explained for humans",
    description:
      "Every new AI paper, translated into something you can actually read.",
    url: SITE_URL,
  },
  twitter: {
    card: "summary_large_image",
    title: "Decoded — AI research, explained for humans",
    description:
      "Every new AI paper, translated into something you can actually read.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body
          className={`${serif.variable} ${sans.variable} ${mono.variable} font-sans antialiased`}
        >
          <PostHogProvider>
            <Providers>
              <div className="flex min-h-screen flex-col">
                <SiteHeader />
                <div className="flex-1">{children}</div>
                <SiteFooter />
              </div>
            </Providers>
          </PostHogProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
