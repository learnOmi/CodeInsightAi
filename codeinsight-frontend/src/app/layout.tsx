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
      <body className="relative">
        {/* 噪点纹理层 — 独立 DOM 避免与 React Flow canvas 的 z-index 冲突 */}
        <div
          className="pointer-events-none fixed inset-0 z-0 opacity-[0.03] dark:opacity-[0.02]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
            backgroundSize: "200px 200px",
          }}
        />
        {/* 品牌光晕 — 暗色模式下屏幕顶部紫色辉光 */}
        <div className="pointer-events-none fixed inset-0 z-0 dark:bg-[radial-gradient(ellipse_at_50%_0%,hsla(247,84%,59%,0.08),transparent_60%)]" />
        <main className="relative z-1">
          <Providers>{children}</Providers>
        </main>
        {/* 主题切换 — 固定在左下角，最高层级 */}
        <div className="fixed bottom-4 left-6 z-[60]">
          <ThemeToggle />
        </div>
      </body>
    </html>
  );
}
