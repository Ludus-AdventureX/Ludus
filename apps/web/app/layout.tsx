import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ludus · Decision Operating System",
  description: "Traceable evidence, structured analysis, causal simulation and human-signed decisions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-theme="ink" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}