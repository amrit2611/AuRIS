import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "AuRIS - Audit Risk Identification System",
  description:
    "Upload any transactions CSV. AuRIS uses an LLM to auto-map your column names, runs six risk checks, scores every row 0-100, ranks the highest-risk rows into a priority queue, and writes a CFO-readable executive summary.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // suppressHydrationWarning on <html>: browser extensions (Dark Reader,
  // Grammarly, colour-management addons, etc.) commonly mutate class or
  // style attributes on <html> before React hydrates, which trips a
  // hydration warning that we cannot fix in application code. The
  // suppression is scoped to this element only and does NOT weaken
  // hydration checks for any child components.
  return (
    <html
      lang="en"
      className={`dark ${inter.variable}`}
      suppressHydrationWarning
    >
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
