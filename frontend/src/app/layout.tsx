import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Jity",
  description: "AI powered RPG scenario console",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
