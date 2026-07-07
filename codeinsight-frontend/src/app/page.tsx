import Link from "next/link";

export default function Home() {
  return (
    <main style={{ maxWidth: 960, margin: "0 auto", padding: "2rem" }}>
      <h1>CodeInsight AI</h1>
      <p>AI 驱动的代码知识提取与可视化分析平台</p>

      <nav>
        <ul>
          <li>
            <Link href="/repositories">仓库管理</Link>
          </li>
          <li>
            <Link href="/knowledge">知识库</Link>
          </li>
          <li>
            <Link href="/search">搜索</Link>
          </li>
        </ul>
      </nav>

      <section>
        <h2>快速开始</h2>
        <ol>
          <li>添加一个本地代码仓库路径</li>
          <li>等待 AI 分析完成</li>
          <li>浏览知识点卡片</li>
        </ol>
      </section>
    </main>
  );
}
