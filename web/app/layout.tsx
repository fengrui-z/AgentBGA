import type { Metadata } from "next";
import "./globals.css";
import "./ark-nova-table.css";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "AgentBGA · Long-Horizon Board-Game Agents",
  description: "Play ten strategy board games with humans and AI agents. Compare agent runtimes, inspect decision traces, and replay matches in one reproducible environment.",
  icons: {icon: `${basePath}/favicon.svg`},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang={process.env.NEXT_PUBLIC_PAGES_RESULTS === "true" ? "en" : "zh-CN"}><body>{children}</body></html>;
}
