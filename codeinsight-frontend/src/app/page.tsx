import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen">
      <div className="mx-auto max-w-5xl px-6 py-16">
        <header className="mb-12">
          <h1 className="text-4xl font-bold tracking-tight">
            <span className="bg-gradient-to-r from-accent to-accent2 bg-clip-text text-transparent">
              CodeInsight AI
            </span>
          </h1>
          <p className="mt-3 text-lg text-muted">
            AI 驱动的代码知识提取与可视化分析平台
          </p>
        </header>

        <section className="mb-12 grid gap-4 sm:grid-cols-3">
          <Link
            href="/repositories"
            className="group rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm transition hover:border-accent/40 hover:shadow-md"
          >
            <div className="text-2xl font-semibold text-[var(--text-primary)]">仓库管理</div>
            <p className="mt-2 text-sm text-muted">
              添加代码仓库，启动 AI 分析
            </p>
          </Link>

          <Link
            href="/knowledge"
            className="group rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm transition hover:border-accent/40 hover:shadow-md"
          >
            <div className="text-2xl font-semibold text-[var(--text-primary)]">知识库</div>
            <p className="mt-2 text-sm text-muted">
              浏览提取的知识点与代码链路
            </p>
          </Link>

          <Link
            href="/search"
            className="group rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-6 shadow-sm transition hover:border-accent/40 hover:shadow-md"
          >
            <div className="text-2xl font-semibold text-[var(--text-primary)]">搜索</div>
            <p className="mt-2 text-sm text-muted">
              全文检索代码与知识点
            </p>
          </Link>
        </section>

        <section className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-8 shadow-sm">
          <h2 className="text-xl font-semibold text-[var(--text-primary)]">快速开始</h2>
          <ol className="mt-4 space-y-2 text-muted">
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-sm font-medium text-accent">
                1
              </span>
              添加一个本地代码仓库路径
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-sm font-medium text-accent">
                2
              </span>
              等待 AI 分析完成
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-sm font-medium text-accent">
                3
              </span>
              浏览知识点卡片
            </li>
          </ol>
        </section>
      </div>
    </main>
  );
}
