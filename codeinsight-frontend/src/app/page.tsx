import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-5xl px-6 py-16">
        {/* 标题区域 — 增加光晕背景 */}
        <header className="mb-16 relative">
          {/* 标题后方光晕 */}
          <div className="absolute -top-8 -left-8 w-64 h-64 rounded-full bg-brand/10 blur-[100px] pointer-events-none" />

          <h1 className="text-5xl font-bold tracking-tight relative">
            <span className="bg-gradient-to-r from-brand via-brand-fg to-status-info bg-clip-text text-transparent">
              CodeInsight AI
            </span>
          </h1>
          <p className="mt-4 text-base text-[var(--text-muted)] max-w-lg leading-relaxed tracking-wide">
            AI 驱动的代码知识提取与可视化分析平台
          </p>
        </header>

        {/* 导航卡片 — 渐变边框 + 辉光 */}
        <section className="mb-16 grid gap-6 sm:grid-cols-3">
          <Link
            href="/repositories"
            className="group relative rounded-2xl overflow-hidden bg-[var(--bg-card)] p-8 transition-all duration-500 hover:-translate-y-2 hover:shadow-[var(--glow-brand-light)]"
          >
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-brand/30 via-brand/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="relative">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">Navigation</div>
              <div className="text-xl font-semibold text-[var(--text-primary)] group-hover:text-brand transition-colors">仓库管理</div>
              <p className="mt-2 text-sm text-[var(--text-muted)] leading-relaxed">
                添加代码仓库，启动 AI 分析
              </p>
              <div className="mt-4 flex items-center gap-1 text-[10px] text-[var(--text-muted)] group-hover:text-brand transition-colors">
                <span>进入</span>
                <span className="transform group-hover:translate-x-0.5 transition-transform">→</span>
              </div>
            </div>
          </Link>

          <Link
            href="/knowledge"
            className="group relative rounded-2xl overflow-hidden bg-[var(--bg-card)] p-8 transition-all duration-500 hover:-translate-y-2 hover:shadow-[var(--glow-brand-light)]"
          >
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-brand/30 via-brand/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="relative">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">Knowledge</div>
              <div className="text-xl font-semibold text-[var(--text-primary)] group-hover:text-brand transition-colors">知识库</div>
              <p className="mt-2 text-sm text-[var(--text-muted)] leading-relaxed">
                浏览提取的知识点与代码链路
              </p>
              <div className="mt-4 flex items-center gap-1 text-[10px] text-[var(--text-muted)] group-hover:text-brand transition-colors">
                <span>进入</span>
                <span className="transform group-hover:translate-x-0.5 transition-transform">→</span>
              </div>
            </div>
          </Link>

          <Link
            href="/search"
            className="group relative rounded-2xl overflow-hidden bg-[var(--bg-card)] p-8 transition-all duration-500 hover:-translate-y-2 hover:shadow-[var(--glow-brand-light)]"
          >
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-brand/30 via-brand/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="relative">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-3">Search</div>
              <div className="text-xl font-semibold text-[var(--text-primary)] group-hover:text-brand transition-colors">搜索</div>
              <p className="mt-2 text-sm text-[var(--text-muted)] leading-relaxed">
                全文检索代码与知识点
              </p>
              <div className="mt-4 flex items-center gap-1 text-[10px] text-[var(--text-muted)] group-hover:text-brand transition-colors">
                <span>进入</span>
                <span className="transform group-hover:translate-x-0.5 transition-transform">→</span>
              </div>
            </div>
          </Link>
        </section>

        {/* 快速开始 — 步骤线样式 */}
        <section className="rounded-2xl bg-[var(--bg-card)] border border-white/[0.06] p-8">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-6">Getting Started</div>
          <ol className="space-y-6">
            <li className="flex items-start gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 text-sm font-semibold text-brand ring-1 ring-brand/20">1</div>
              <div>
                <div className="text-sm font-medium text-[var(--text-primary)]">添加本地仓库路径</div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5">支持文件系统目录或 Git URL</div>
              </div>
            </li>
            <li className="flex items-start gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 text-sm font-semibold text-brand ring-1 ring-brand/20">2</div>
              <div>
                <div className="text-sm font-medium text-[var(--text-primary)]">等待 AI 分析完成</div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5">系统自动解析代码结构与依赖关系</div>
              </div>
            </li>
            <li className="flex items-start gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/10 text-sm font-semibold text-brand ring-1 ring-brand/20">3</div>
              <div>
                <div className="text-sm font-medium text-[var(--text-primary)]">浏览知识点卡片</div>
                <div className="text-xs text-[var(--text-muted)] mt-0.5">查看函数、类、接口及其调用链路</div>
              </div>
            </li>
          </ol>
        </section>
      </div>
    </main>
  );
}