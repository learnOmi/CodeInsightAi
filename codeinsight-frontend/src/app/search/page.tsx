import { ArrowLeft } from "lucide-react";
import Link from "next/link";

export default function SearchPage() {
  return (
    <>
      {/* 返回按钮 — 固定在左上角 */}
      <div className="fixed top-4 left-6 z-50">
        <Link
          href="/"
          className="flex items-center gap-2 p-2 bg-[var(--bg-card)] border border-[var(--border)] rounded-lg hover:bg-[var(--bg-hover)] transition-colors shadow-sm"
        >
          <ArrowLeft className="w-4 h-4 text-[var(--text-secondary)]" />
          <span className="text-sm text-[var(--text-primary)]">返回</span>
        </Link>
      </div>

      <main className="mx-auto max-w-5xl px-6 py-12 pt-16">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-[var(--text-primary)]">搜索</h1>
          <p className="mt-2 text-muted">全文检索代码与知识点</p>
        </header>

        <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-12 text-center shadow-sm">
          <div className="text-muted">
            功能开发中 — Phase 4 将上线搜索功能
          </div>
        </div>
      </main>
    </>
  );
}
