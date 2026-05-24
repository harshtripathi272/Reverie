import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reverie — Cognitive observability for AI agents",
  description:
    "A 3D spatial debugger for AI agent runs. Replay, navigate, and compare " +
    "the cognition of autonomous agents.",
};

export const viewport: Viewport = {
  themeColor: "#000000",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-black text-zinc-200 antialiased">{children}</body>
    </html>
  );
}
