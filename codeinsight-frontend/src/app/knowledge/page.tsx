import { ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function KnowledgePage() {
  return (
    <>
      {/* 返回按钮 — 固定在左上角 */}
      <div className="fixed top-4 left-6 z-50">
        <Link
          href="/"
          className="flex items-center gap-2 p-2 bg-[var(--bg-card)]/70 backdrop-blur-xl border border-white/[0.06] rounded-lg hover:bg-[var(--bg-hover)] transition-colors shadow-sm"
        >
          <ArrowLeft className="w-4 h-4 text-[var(--text-secondary)]" />
          <span className="text-sm text-[var(--text-primary)]">返回</span>
        </Link>
      </div>

      <main className="mx-auto max-w-5xl px-6 py-16">
        <header className="mb-12 relative">
          {/* 标题后方光晕 */}
          <div className="absolute -top-8 -left-8 w-64 h-64 rounded-full bg-brand/10 blur-[100px] pointer-events-none" />
          <h1 className="text-5xl font-bold tracking-tight relative">
            <span className="bg-gradient-to-r from-brand via-brand-fg to-status-info bg-clip-text text-transparent">
              知识库
            </span>
          </h1>
          <p className="mt-3 text-base text-[var(--text-muted)] max-w-lg leading-relaxed tracking-wide">
            浏览从代码中提取的知识点与设计模式
          </p>
        </header>

        <div className="rounded-2xl border border-white/[0.06] bg-[var(--bg-card)] p-12 text-center shadow-sm">
          <div className="text-[var(--text-muted)]">
            功能开发中 — Phase 3 将上线知识点展示功能
          </div>
        </div>
      </main>
    </>
  );
}