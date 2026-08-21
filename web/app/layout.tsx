import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {default: "AgentBGA · Long-Horizon Game Arena", template: "%s · AgentBGA"},
  description: "Configure humans and model harnesses, then inspect their board-game decisions live.",
  icons: {icon: "/favicon.svg"},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
