import type { Metadata } from "next";
import "./globals.css";
import "./ark-nova-workbench.css";
import "./ark-nova-table.css";

const title = "AgentBGA · Semantic Board Game Arena";
const description = "Inspect auditable board-game content, semantic rules, and long-horizon agent decisions.";

export const metadata: Metadata = {
  metadataBase: new URL("https://agentbga-semantic-arena.xiangli0233.chatgpt.site"),
  title,
  description,
  icons: {icon: "/favicon.svg"},
  openGraph: {title, description, type: "website", images: [{url: "/og.png", width: 1731, height: 909}]},
  twitter: {card: "summary_large_image", title, description, images: ["/og.png"]},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
