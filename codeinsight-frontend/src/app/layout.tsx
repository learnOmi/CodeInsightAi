import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { Providers } from "./providers";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "CodeInsight AI",
  description: "AI 驱动的代码知识提取与可视化分析平台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
        {/* 主题切换 — 固定在左下角，最高层级 */}
        <div className="fixed bottom-4 left-6 z-[60]">
          <ThemeToggle />
        </div>
      </body>
    </html>
  );
}
