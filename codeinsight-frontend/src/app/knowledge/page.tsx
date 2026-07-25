"use client";

import { useState, useMemo } from "react";
import { ArrowLeft, BookOpen, Search, Filter, X, ChevronDown, ExternalLink, Tag, Layers, Sparkles, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getKnowledgePoints, getKnowledgeStats } from "@/api/knowledge";
import { useRepositories } from "@/hooks/use-repositories";
import { KNOWLEDGE_CATEGORY_NAMES, KNOWLEDGE_CATEGORY_COLORS } from "@codeinsight/shared";
import type { components } from "@codeinsight/shared";

type KnowledgePoint = components["schemas"]["KnowledgePoint"];
type ExpansionContent = components["schemas"]["ExpansionContent"];
type KnowledgeCategory = components["schemas"]["KnowledgeCategory"];

const CATEGORIES: KnowledgeCategory[] = ["DP-", "AD-", "AL-", "ET-", "DK-"];

/** 标准化分类值：确保以 "-" 结尾 */
function normalizeCategory(cat: string): KnowledgeCategory {
  return (cat.endsWith("-") ? cat : `${cat}-`) as KnowledgeCategory;
}

/** 分类标签组件 */
function CategoryBadge({ category }: { category: string }) {
  const normalized = normalizeCategory(category);
  const color = KNOWLEDGE_CATEGORY_COLORS[normalized] ?? "#6b7280";
  const name = KNOWLEDGE_CATEGORY_NAMES[normalized] ?? category;
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{
        backgroundColor: `${color}18`,
        color,
        border: `1px solid ${color}30`,
      }}
    >
      {name}
    </span>
  );
}

/** 置信度指示器 */
function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 80 ? "bg-status-success" : pct >= 50 ? "bg-yellow-500" : "bg-status-error";
  return (
    <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
      <div className="h-1.5 w-16 rounded-full bg-white/[0.06] overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span>{pct}%</span>
    </div>
  );
}

/** 知识库卡片 */
function KnowledgeCard({
  kp,
  onSelect,
}: {
  kp: KnowledgePoint;
  onSelect: (kp: KnowledgePoint) => void;
}) {
  return (
    <button
      onClick={() => onSelect(kp)}
      className="group relative w-full text-left rounded-2xl border border-white/[0.06] bg-[var(--bg-card)] p-5 transition-all duration-300 hover:border-white/[0.12] hover:shadow-md hover:-translate-y-0.5"
    >
      {/* 顶部：分类 + 置信度 */}
      <div className="flex items-center justify-between mb-3">
        <CategoryBadge category={kp.category} />
        <ConfidenceBar confidence={kp.confidence} />
      </div>

      {/* 标题 */}
      <h3 className="text-base font-semibold text-[var(--text-primary)] group-hover:text-brand transition-colors line-clamp-2">
        {kp.title}
      </h3>

      {/* 描述 */}
      <p className="mt-1.5 text-sm text-[var(--text-muted)] line-clamp-2 leading-relaxed">
        {kp.description}
      </p>

      {/* 标签 */}
      {kp.tags && kp.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {kp.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 rounded-md bg-white/[0.04] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
            >
              <Tag className="w-3 h-3" />
              {tag}
            </span>
          ))}
          {kp.tags.length > 4 && (
            <span className="text-[11px] text-[var(--text-muted)]">+{kp.tags.length - 4}</span>
          )}
        </div>
      )}

      {/* 底部：代码片段数 */}
      {kp.codeSnippets && kp.codeSnippets.length > 0 && (
        <div className="mt-3 flex items-center gap-1 text-xs text-[var(--text-muted)]">
          <Layers className="w-3.5 h-3.5" />
          <span>{kp.codeSnippets.length} 个代码片段</span>
        </div>
      )}
    </button>
  );
}

/** 拓展内容展示面板 */
function ExpansionPanel({ expansion }: { expansion: ExpansionContent | null }) {
  if (!expansion) {
    return (
      <div className="text-sm text-[var(--text-muted)] italic">
        暂无拓展内容
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 核心原理 */}
      {expansion.principle && (
        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2 flex items-center gap-1.5">
            <Sparkles className="w-4 h-4 text-brand" />
            核心原理
          </h4>
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
            {expansion.principle}
          </p>
        </section>
      )}

      {/* 适用场景 */}
      {expansion.applicableScenarios && expansion.applicableScenarios.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2">适用场景</h4>
          <ul className="space-y-1.5">
            {expansion.applicableScenarios.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/60" />
                {s}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 最佳实践 */}
      {expansion.bestPractices && expansion.bestPractices.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2">最佳实践</h4>
          <ul className="space-y-1.5">
            {expansion.bestPractices.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-[var(--text-secondary)]">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-status-success/60" />
                {p}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* 关联模式 */}
      {expansion.relatedPatterns && expansion.relatedPatterns.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2">关联技术/模式</h4>
          <div className="flex flex-wrap gap-2">
            {expansion.relatedPatterns.map((r, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-lg bg-white/[0.04] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
              >
                {r}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* 学习资源 */}
      {expansion.learningResources && expansion.learningResources.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2">学习资源</h4>
          <div className="space-y-2">
            {expansion.learningResources.map((r, i) => (
              <a
                key={i}
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-white/[0.06] transition-colors group"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs uppercase font-medium text-[var(--text-muted)] shrink-0">
                    {resourceTypeLabel(r.type)}
                  </span>
                  <span className="truncate">{r.title}</span>
                </div>
                <ExternalLink className="w-3.5 h-3.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function resourceTypeLabel(type: string): string {
  const map: Record<string, string> = {
    book: "📖 书籍",
    article: "📄 文章",
    video: "🎬 视频",
    course: "🎓 课程",
  };
  return map[type] ?? type;
}

/** 知识点详情弹窗 */
function KnowledgeDetailModal({
  kp,
  onClose,
}: {
  kp: KnowledgePoint;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 pt-12 pb-12">
      <div className="relative w-full max-w-3xl mx-4 rounded-2xl border border-white/[0.08] bg-[var(--bg-card)] shadow-2xl">
        {/* 关闭按钮 */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white/[0.06] transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* 头部 */}
        <div className="p-6 pb-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-2 mb-3">
            <CategoryBadge category={kp.category} />
            <ConfidenceBar confidence={kp.confidence} />
          </div>
          <h2 className="text-xl font-bold text-[var(--text-primary)]">{kp.title}</h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)] leading-relaxed">
            {kp.description}
          </p>
          {kp.tags && kp.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {kp.tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 rounded-md bg-white/[0.04] px-2 py-0.5 text-xs text-[var(--text-secondary)]"
                >
                  <Tag className="w-3 h-3" />
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 拓展内容 */}
        <div className="p-6">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-4">
            拓展内容
          </h3>
          <ExpansionPanel expansion={kp.expansion} />
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  const [selectedCategory, setSelectedCategory] = useState<KnowledgeCategory | "all">("all");
  const [selectedRepoId, setSelectedRepoId] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedKp, setSelectedKp] = useState<KnowledgePoint | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const { data: repos } = useRepositories();
  const activeRepoId = selectedRepoId !== "all" ? selectedRepoId : (repos?.[0]?.id ?? "");

  const { data: statsData } = useQuery({
    queryKey: ["knowledge-stats", activeRepoId],
    queryFn: () => getKnowledgeStats(activeRepoId),
    enabled: !!activeRepoId,
  });

  const { data: kpData, isLoading } = useQuery({
    queryKey: ["knowledge-points", activeRepoId, selectedCategory, page],
    queryFn: () =>
      getKnowledgePoints({
        repositoryId: activeRepoId,
        category: selectedCategory !== "all" ? selectedCategory.replace(/-$/, "") : undefined,
        page,
        pageSize: 12,
      }),
    enabled: !!activeRepoId,
  });

  // 客户端搜索过滤
  const filteredKps = useMemo(() => {
    if (!kpData?.items) return [];
    if (!searchQuery.trim()) return kpData.items;
    const q = searchQuery.toLowerCase();
    return kpData.items.filter(
      (kp) =>
        kp.title.toLowerCase().includes(q) ||
        kp.description.toLowerCase().includes(q) ||
        kp.tags?.some((t) => t.toLowerCase().includes(q))
    );
  }, [kpData, searchQuery]);

  const totalPages = kpData ? Math.max(1, Math.ceil(kpData.total / kpData.pageSize)) : 1;

  return (
    <>
      {/* 返回按钮 */}
      <div className="fixed top-4 left-6 z-50">
        <Link
          href="/"
          className="flex items-center gap-2 p-2 bg-[var(--bg-card)]/70 backdrop-blur-xl border border-white/[0.06] rounded-lg hover:bg-[var(--bg-hover)] transition-colors shadow-sm"
        >
          <ArrowLeft className="w-4 h-4 text-[var(--text-secondary)]" />
          <span className="text-sm text-[var(--text-primary)]">返回</span>
        </Link>
      </div>

      <main className="mx-auto max-w-7xl px-6 py-16">
        {/* 标题 */}
        <header className="mb-10 relative">
          <div className="absolute -top-8 -left-8 w-64 h-64 rounded-full bg-brand/10 blur-[100px] pointer-events-none" />
          <div className="flex items-center gap-3 mb-3">
            <BookOpen className="w-8 h-8 text-brand" />
            <h1 className="text-5xl font-bold tracking-tight relative">
              <span className="bg-gradient-to-r from-brand via-brand-fg to-status-info bg-clip-text text-transparent">
                知识库
              </span>
            </h1>
          </div>
          <p className="mt-2 text-base text-[var(--text-muted)] max-w-xl leading-relaxed tracking-wide">
            浏览从代码中提取的知识点与设计模式，查看 AI 生成的拓展内容
          </p>
          {statsData && (
            <div className="mt-4 flex items-center gap-4 text-sm text-[var(--text-muted)]">
              <span>共 {statsData.totalPoints} 个知识点</span>
              {Object.entries(statsData.byCategory).map(([cat, count]) => {
                const normalized = normalizeCategory(cat);
                return (
                  <span key={cat} className="flex items-center gap-1">
                    <span
                      className="inline-block w-2 h-2 rounded-full"
                      style={{ backgroundColor: KNOWLEDGE_CATEGORY_COLORS[normalized] ?? "#6b7280" }}
                    />
                    {KNOWLEDGE_CATEGORY_NAMES[normalized] ?? cat} {count}
                  </span>
                );
              })}
            </div>
          )}
        </header>

        {/* 筛选工具栏 */}
        <div className="mb-8 space-y-4">
          {/* 第一行：仓库选择 + 搜索 */}
          <div className="flex flex-col sm:flex-row gap-4">
            {/* 仓库选择 */}
            <div className="relative flex-1 max-w-xs">
              <select
                value={selectedRepoId}
                onChange={(e) => { setSelectedRepoId(e.target.value); setPage(1); }}
                className="w-full appearance-none rounded-xl border border-white/[0.08] bg-[var(--bg-card)] px-4 py-2.5 pr-10 text-sm text-[var(--text-primary)] focus:outline-none focus:border-brand/50 transition-colors"
              >
                <option value="all">所有仓库</option>
                {repos?.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)] pointer-events-none" />
            </div>

            {/* 搜索框 */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索知识点标题、描述或标签..."
                className="w-full rounded-xl border border-white/[0.08] bg-[var(--bg-card)] pl-10 pr-4 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-brand/50 transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* 筛选按钮（移动端） */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/[0.08] bg-[var(--bg-card)] text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors sm:hidden"
            >
              <Filter className="w-4 h-4" />
              分类筛选
            </button>
          </div>

          {/* 分类筛选 */}
          <div className={`flex flex-wrap gap-2 ${showFilters ? "flex" : "hidden sm:flex"}`}>
            <button
              onClick={() => { setSelectedCategory("all"); setPage(1); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                selectedCategory === "all"
                  ? "bg-brand/20 text-brand border border-brand/30"
                  : "bg-white/[0.04] text-[var(--text-secondary)] border border-transparent hover:bg-white/[0.08]"
              }`}
            >
              全部
            </button>
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => { setSelectedCategory(cat); setPage(1); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  selectedCategory === cat
                    ? "bg-brand/20 text-brand border border-brand/30"
                    : "bg-white/[0.04] text-[var(--text-secondary)] border border-transparent hover:bg-white/[0.08]"
                }`}
                style={selectedCategory === cat ? {
                  backgroundColor: `${KNOWLEDGE_CATEGORY_COLORS[cat]}18`,
                  color: KNOWLEDGE_CATEGORY_COLORS[cat],
                  borderColor: `${KNOWLEDGE_CATEGORY_COLORS[cat]}30`,
                } : undefined}
              >
                {KNOWLEDGE_CATEGORY_NAMES[cat]}
              </button>
            ))}
          </div>
        </div>

        {/* 知识点列表 */}
        {isLoading ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="rounded-2xl border border-white/[0.06] bg-[var(--bg-card)] p-5 animate-pulse"
              >
                <div className="h-4 w-20 bg-white/[0.06] rounded mb-3" />
                <div className="h-5 w-3/4 bg-white/[0.06] rounded mb-2" />
                <div className="h-4 w-full bg-white/[0.06] rounded mb-1" />
                <div className="h-4 w-2/3 bg-white/[0.06] rounded" />
              </div>
            ))}
          </div>
        ) : filteredKps.length === 0 ? (
          <div className="rounded-2xl border border-white/[0.06] bg-[var(--bg-card)] p-12 text-center">
            <BookOpen className="w-12 h-12 mx-auto text-[var(--text-muted)] mb-4" />
            <div className="text-lg font-medium text-[var(--text-primary)]">暂无知识点</div>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {searchQuery
                ? "没有匹配搜索条件的知识点，请尝试其他关键词"
                : "请先添加仓库并完成 AI 分析"}
            </p>
          </div>
        ) : (
          <>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {filteredKps.map((kp) => (
                <KnowledgeCard key={kp.id} kp={kp} onSelect={setSelectedKp} />
              ))}
            </div>

            {/* 分页 */}
            {totalPages > 1 && (
              <div className="mt-8 flex items-center justify-center gap-3">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="flex items-center gap-1 px-3 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-white/[0.06] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4" />
                  上一页
                </button>
                <span className="text-sm text-[var(--text-muted)]">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 px-3 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-white/[0.06] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  下一页
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </>
        )}
      </main>

      {/* 详情弹窗 */}
      {selectedKp && (
        <KnowledgeDetailModal kp={selectedKp} onClose={() => setSelectedKp(null)} />
      )}
    </>
  );
}