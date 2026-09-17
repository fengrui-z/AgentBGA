import type { Metadata } from "next";
import "./globals.css";
import "./ark-nova-table.css";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "AgentBGA · Long-Horizon Board-Game Agents",
  description: "A deterministic, auditable environment for evaluating model × harness agents in long-horizon Euro-style board games.",
  icons: {icon: `${basePath}/favicon.svg`},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
