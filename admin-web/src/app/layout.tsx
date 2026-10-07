import type { Metadata, Viewport } from "next";
import { ClaudeConnectionBadge } from "@/components/app/ClaudeConnectionBadge";
import { RegisterServiceWorker } from "@/components/app/RegisterServiceWorker";
import "./globals.css";

export const metadata: Metadata = {
  title: "Haehan AI Admin",
  description: "Haehan AI Orchestrator Admin",
  applicationName: "Haehan AI Admin",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/icon.svg",
    apple: "/icon.svg",
  },
  appleWebApp: {
    capable: true,
    title: "Haehan AI",
    statusBarStyle: "default",
  },
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#F97316",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        <RegisterServiceWorker />
        {children}
        <ClaudeConnectionBadge />
      </body>
    </html>
  );
}
