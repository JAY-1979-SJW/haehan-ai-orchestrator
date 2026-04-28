import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Haehan AI Admin",
  description: "Haehan AI Orchestrator Admin",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
