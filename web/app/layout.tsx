import type { Metadata } from "next";
import "./globals.css";
import "./ark-nova-workbench.css";
import "./ark-nova-table.css";

const title = "AgentBGA · Long-Horizon Game Arena";
const description = "Compare model and harness configurations across long-horizon board-game tournaments.";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title,
  description,
  icons: {icon: `${basePath}/favicon.svg`},
  openGraph: {title, description, type: "website", images: [`${basePath}/og.png`]},
  twitter: {card: "summary_large_image", title, description, images: [`${basePath}/og.png`]},
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
