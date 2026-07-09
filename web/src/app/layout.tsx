import type { Metadata } from "next";
import "./globals.css";

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
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
