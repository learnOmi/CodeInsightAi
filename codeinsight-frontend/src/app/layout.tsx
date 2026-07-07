import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CodeInsight AI",
  description: "AI 驱动的代码知识提取与可视化分析平台",
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
