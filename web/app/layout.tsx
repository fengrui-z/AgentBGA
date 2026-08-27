import type { Metadata } from "next";
import "./globals.css";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "AgentBGA · Long-Horizon Game Arena",
  description: "Compare model and harness configurations across long-horizon board-game tournaments.",
  icons: {icon: `${basePath}/favicon.svg`},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
