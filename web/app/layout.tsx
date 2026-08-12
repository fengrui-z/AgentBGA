import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgentBGA · Splendor Live Table",
  description: "Configure multiple LLMs and watch their Splendor decisions live.",
  icons: {icon: "/favicon.svg"},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
