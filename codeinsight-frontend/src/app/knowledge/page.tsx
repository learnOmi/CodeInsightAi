"use client";

import { useState, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  Search,
  Filter,
  X,
  ChevronDown,
  ExternalLink,
  Tag,
  Sparkles,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import NextLink from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getKnowledgePoints, getKnowledgeStats } from "@/api/knowledge";
import { useRepositories } from "@/hooks/use-repositories";
import { GlobalNav } from "@/components/GlobalNav";
import { KNOWLEDGE_CATEGORY_COLORS } from "@codeinsight/shared";
import type { components } from "@codeinsight/shared";

type KnowledgePoint = components["schemas"]["KnowledgePoint"];
type ExpansionContent = components["schemas"]["ExpansionContent"];

// ── Helpers ─────────────────────────────────────────────────────────────────

const CATEGORY_COLORS = KNOWLEDGE_CATEGORY_COLORS as Record<string, string>;

function getCatColor(cat: string): string {
  return CATEGORY_COLORS[cat] ?? "#6b7280";
}

const CATEGORY_LABELS: Record<string, string> = {
  DP: "设计模式",
  AD: "架构决策",
  AL: "算法实现",
  ET: "工程技巧",
  DK: "领域知识",
  TT: "开发模板",
  TK: "技术栈",
};

function resourceTypeLabel(type: string): string {
  const map: Record<string, string> = {
    book: "书籍",
    article: "文章",
    video: "视频",
    course: "课程",
  };
  return map[type] ?? type;
}

// ── Sub-components ──────────────────────────────────────────────────────────

function CategoryPill({ category }: { category: string }) {
  const color = getCatColor(category);
  const label = CATEGORY_LABELS[category] ?? category;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all"
      style={{
        backgroundColor: `${color}12`,
        color,
        border: `1px solid ${color}28`,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  );
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    pct >= 80 ? "bg-emerald-400" : pct >= 50 ? "bg-amber-400" : "bg-red-400";
  const textColor =
    pct >= 80 ? "text-emerald-400" : pct >= 50 ? "text-amber-400" : "text-red-400";
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="h-1.5 w-14 rounded-full bg-white/[0.08] overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <span className={textColor}>{pct}%</span>
    </div>
  );
}

// ── KnowledgeCard ───────────────────────────────────────────────────────────

function KnowledgeCard({
  kp,
  onSelect,
}: {
  kp: KnowledgePoint;
  onSelect: (kp: KnowledgePoint) => void;
}) {
  const catColor = getCatColor(kp.category);
  const hasTags = kp.tags && kp.tags.length > 0;

  return (
    <div
      className="group relative flex flex-col w-full overflow-hidden rounded-2xl bg-[var(--bg-card)] border border-white/[0.05] p-5 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl cursor-default"
      style={{
        borderColor: `color-mix(in srgb, ${catColor} 8%, transparent)`,
      }}
    >
      {/* Top accent bar */}
      <div
        className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl transition-all duration-300 group-hover:h-1.5"
        style={{ backgroundColor: catColor }}
      />

      {/* 头部：分类 + 置信度 */}
      <div className="flex items-center justify-between mb-4 pt-2">
        <CategoryPill category={kp.category} />
        <ConfidenceBar confidence={kp.confidence} />
      </div>

      {/* 标题 */}
      <h3
        onClick={() => onSelect(kp)}
        className="cursor-pointer text-lg font-bold text-[var(--text-primary)] leading-snug line-clamp-2 transition-colors duration-200 group-hover:text-brand"
      >
        {kp.title}
      </h3>

      {/* 描述 */}
      <p className="mt-2 text-[13px] text-[var(--text-muted)] leading-relaxed line-clamp-3">
        {kp.description}
      </p>

      {/* 标签 */}
      {hasTags && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {kp.tags!.slice(0, 3).map((tag: string) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-[var(--text-secondary)] bg-white/[0.04]"
            >
              <Tag className="w-2.5 h-2.5" />
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* 底部 CTA */}
      <div className="mt-auto pt-5">
        <NextLink
          href={`/knowledge/${kp.id}`}
          className="relative flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium overflow-hidden transition-all duration-300 group/link"
          style={{
            color: catColor,
            backgroundColor: `${catColor}10`,
            border: `1px solid ${catColor}20`,
          }}
        >
          <span className="relative z-10">查看详情</span>
          <ArrowLeft className="w-3.5 h-3.5 relative z-10 rotate-180 transition-transform duration-300 group-hover/link:-translate-x-0.5" />
        </NextLink>
      </div>
    </div>
  );
}

// ── ExpansionPanel ──────────────────────────────────────────────────────────

function ExpansionPanel({ expansion }: { expansion: ExpansionContent | null }) {
  if (!expansion) {
    return (
      <div className="text-center py-10">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white/[0.03] mb-3">
          <Sparkles className="w-5 h-5 text-[var(--text-muted)]" />
        </div>
        <p className="text-sm text-[var(--text-muted)]">暂无 AI 拓展内容</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {expansion.principle && (
        <div className="rounded-xl bg-brand/[0.04] border border-brand/[0.1] p-4">
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-brand" /> 核心原理
          </h4>
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
            {expansion.principle}
          </p>
        </div>
      )}

      {expansion.applicableScenarios?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">适用场景</h4>
          <div className="space-y-1.5">
            {expansion.applicableScenarios.map((s: string, i: number) => (
              <div key={i} className="flex items-start gap-2.5 rounded-lg bg-white/[0.02] px-3 py-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/60" />
                <span className="text-sm text-[var(--text-secondary)]">{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {expansion.bestPractices?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">最佳实践</h4>
          <div className="space-y-1.5">
            {expansion.bestPractices.map((p: string, i: number) => (
              <div key={i} className="flex items-start gap-2.5 rounded-lg bg-white/[0.02] px-3 py-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400/70" />
                <span className="text-sm text-[var(--text-secondary)]">{p}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {expansion.relatedPatterns?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">关联技术/模式</h4>
          <div className="flex flex-wrap gap-1.5">
            {expansion.relatedPatterns.map((r: string, i: number) => (
              <span
                key={i}
                className="inline-flex items-center rounded-lg bg-white/[0.04] border border-white/[0.06] px-2.5 py-1 text-xs text-[var(--text-secondary)] transition-colors hover:bg-white/[0.08]"
              >
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {expansion.learningResources?.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-2.5">学习资源</h4>
          <div className="space-y-1.5">
            {expansion.learningResources.map((r, i: number) => (
              <a
                key={i}
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-lg bg-white/[0.02] border border-white/[0.04] px-3 py-2.5 text-sm text-[var(--text-secondary)] hover:bg-white/[0.05] transition-all group"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-[10px] uppercase font-semibold text-[var(--text-muted)] shrink-0 w-12">
                    {resourceTypeLabel(r.type)}
                  </span>
                  <span className="truncate">{r.title}</span>
                </div>
                <ExternalLink className="w-3.5 h-3.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-brand" />
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── KnowledgeDetailModal ────────────────────────────────────────────────────

function KnowledgeDetailModal({
  kp,
  onClose,
}: {
  kp: KnowledgePoint;
  onClose: () => void;
}) {
  const catColor = getCatColor(kp.category);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 pt-12 pb-12 backdrop-blur-sm">
      <div
        className="relative w-full max-w-2xl mx-4 rounded-2xl border bg-[var(--bg-card)] shadow-2xl overflow-hidden"
        style={{ borderColor: `${catColor}18` }}
      >
        {/* Top accent */}
        <div className="absolute top-0 left-0 right-0 h-1" style={{ backgroundColor: catColor }} />

        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white/[0.06] transition-colors z-10"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="p-6 pb-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-2 mb-3">
            <CategoryPill category={kp.category} />
            <ConfidenceBar confidence={kp.confidence} />
          </div>
          <h2 className="text-xl font-bold text-[var(--text-primary)] leading-tight">{kp.title}</h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)] leading-relaxed">
            {kp.description}
          </p>
          {kp.tags?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {kp.tags.map((tag: string) => (
                <span key={tag} className="inline-flex items-center gap-1 rounded-md bg-white/[0.04] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                  <Tag className="w-3 h-3" />
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="p-6">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-4 flex items-center gap-1.5">
            <Sparkles className="w-4 h-4" /> 拓展内容
          </h3>
          <ExpansionPanel expansion={kp.expansion || null} />
        </div>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  const CATEGORIES = [
    { key: "all", label: "全部" },
    { key: "DP", label: "设计模式" },
    { key: "AD", label: "架构决策" },
    { key: "AL", label: "算法实现" },
    { key: "ET", label: "工程技巧" },
    { key: "DK", label: "领域知识" },
  ];

  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedRepoId = searchParams.get("repositoryId") ?? "all";
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedKp, setSelectedKp] = useState<KnowledgePoint | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  // 仓库切换：更新 URL 参数
  const handleRepoChange = (newRepoId: string) => {
    setPage(1);
    const params = new URLSearchParams(searchParams);
    if (newRepoId === "all") {
      params.delete("repositoryId");
    } else {
      params.set("repositoryId", newRepoId);
    }
    const query = params.toString();
    router.push(query ? `/knowledge?${query}` : "/knowledge");
  };

  const { data: repos } = useRepositories(1, 30);
  const queryRepoId = selectedRepoId === "all" ? "" : selectedRepoId;

  const { data: statsData } = useQuery({
    queryKey: ["knowledge-stats", selectedRepoId],
    queryFn: () => getKnowledgeStats(selectedRepoId === "all" ? "" : selectedRepoId),
    enabled: true,
  });

  const { data: kpData, isLoading } = useQuery({
    queryKey: ["knowledge-points", selectedRepoId, selectedCategory, page],
    queryFn: () =>
      getKnowledgePoints({
        repositoryId: queryRepoId,
        category: selectedCategory !== "all" ? selectedCategory : undefined,
        page,
        pageSize: 12,
      }),
    enabled: true,
  });

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

  const points = useMemo(() => filteredKps, [filteredKps]);
  // 分页计算：搜索时基于过滤后的结果数量重新计算总页数，否则使用总知识点数除以每页数量
  const totalPages = useMemo(() => {
    if (!kpData) return 1;
    
    // 确定要使用的总知识点数
    let total: number;
    if (selectedRepoId !== "all") {
      // 指定仓库时使用 kpData 中的精确值（与仓库过滤匹配）
      total = kpData.total || 0;
    } else {
      // "所有仓库" 时优先使用 statsData（如果已就绪），否则回退到 kpData
      if (statsData && statsData.totalPoints !== undefined) {
        total = statsData.totalPoints;
      } else {
        total = kpData.total || 0;
      }
    }

    // 获取每页大小
    const pageSize = Math.max(1, Number(kpData.pageSize) || 12);
    
    if (searchQuery.trim()) {
      return Math.max(1, Math.ceil(filteredKps.length / pageSize));
    }
    return Math.max(1, Math.ceil(total / pageSize));
  }, [kpData, selectedRepoId, statsData, filteredKps, searchQuery]);

  return (
    <>
      {/* 背景装饰 */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute top-[-20%] right-[-10%] w-[600px] h-[600px] rounded-full bg-brand/[0.04] blur-[120px]" />
        <div className="absolute bottom-[-20%] left-[-10%] w-[500px] h-[500px] rounded-full bg-purple-500/[0.04] blur-[120px]" />
      </div>

      {/* 全局导航栏 */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        <GlobalNav />
      </div>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {/* 标题区 */}
        <header className="mb-10">
          <div className="flex items-center gap-3 mb-3">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-brand/[0.1]">
              <BookOpen className="w-6 h-6 text-brand" />
            </div>
            <h1 className="text-5xl font-bold tracking-tight">
              <span className="bg-gradient-to-r from-brand via-violet-400 to-sky-400 bg-clip-text text-transparent">
                知识库
              </span>
            </h1>
          </div>
          <p className="mt-2 text-base text-[var(--text-muted)] max-w-xl leading-relaxed">
            浏览从代码中提取的知识点与设计模式，查看项目中的应用方式与 AI 拓展内容
          </p>
          {statsData && (
            <div className="mt-5 flex flex-wrap items-center gap-4 text-sm">
              <span className="text-[var(--text-primary)] font-medium">
                共 {statsData.totalPoints} 个知识点
              </span>
              {Object.entries(statsData.byCategory).map(([cat, count]) => (
                <span key={cat} className="inline-flex items-center gap-1.5">
                  <span
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ backgroundColor: getCatColor(cat) }}
                  />
                  <span className="text-[var(--text-muted)]">
                    {CATEGORY_LABELS[cat] ?? cat} {count}
                  </span>
                </span>
              ))}
            </div>
          )}
        </header>

        {/* 筛选工具栏 */}
        <div className="mb-8 space-y-3">
          <div className="flex flex-col sm:flex-row gap-3">
            {/* 仓库选择 */}
            <div className="relative flex-1 max-w-xs">
              <select
                value={selectedRepoId}
                onChange={(e) => handleRepoChange(e.target.value)}
                className="w-full appearance-none rounded-xl border border-white/[0.06] bg-[var(--bg-card)]/50 backdrop-blur px-4 py-2.5 pr-10 text-sm text-[var(--text-primary)] focus:outline-none focus:border-brand/40 transition-colors"
              >
                <option value="all">所有仓库</option>
                {repos?.items?.map((repo) => (
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
                placeholder="搜索知识点..."
                className="w-full rounded-xl border border-white/[0.06] bg-[var(--bg-card)]/50 backdrop-blur pl-10 pr-4 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-brand/40 transition-colors"
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

            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/[0.06] bg-[var(--bg-card)]/50 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors sm:hidden"
            >
              <Filter className="w-4 h-4" />
              分类
            </button>
          </div>

          {/* 分类筛选 */}
          <div className={`flex flex-wrap gap-2 ${showFilters ? "flex" : "hidden sm:flex"}`}>
            {CATEGORIES.map((cat) => {
              const isActive = selectedCategory === cat.key;
              const catColor = cat.key !== "all" ? getCatColor(cat.key) : undefined;
              return (
                <button
                  key={cat.key}
                  onClick={() => { setSelectedCategory(cat.key); setPage(1); }}
                  className={`relative px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                    isActive
                      ? "border"
                      : "bg-white/[0.03] text-[var(--text-secondary)] border border-transparent hover:bg-white/[0.06]"
                  }`}
                  style={isActive ? {
                    color: catColor,
                    backgroundColor: `${catColor}10`,
                    borderColor: `${catColor}30`,
                  } : {}}
                >
                  {cat.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* 知识点列表 */}
        {isLoading ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i: number) => (
              <div
                key={i}
                className="rounded-2xl border border-white/[0.05] bg-[var(--bg-card)] p-5 animate-pulse"
              >
                <div className="h-1 rounded mb-3 bg-white/[0.06]" />
                <div className="h-5 w-20 rounded mb-4 bg-white/[0.06]" />
                <div className="h-5 w-3/4 rounded mb-2 bg-white/[0.06]" />
                <div className="h-4 w-full rounded mb-1 bg-white/[0.06]" />
                <div className="h-4 w-2/3 rounded bg-white/[0.06]" />
              </div>
            ))}
          </div>
        ) : points.length === 0 ? (
          <div className="rounded-2xl border border-white/[0.05] bg-[var(--bg-card)] p-12 text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-white/[0.03] mb-4">
              <BookOpen className="w-7 h-7 text-[var(--text-muted)]" />
            </div>
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
              {points.map((kp) => (
                <KnowledgeCard key={kp.id} kp={kp} onSelect={setSelectedKp} />
              ))}
            </div>

            {/* 分页 */}
            {totalPages > 1 && (
              <div className="mt-10 flex items-center justify-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="flex items-center gap-1 px-3.5 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-white/[0.05] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4 h-4" />
                  上一页
                </button>
                <span className="px-4 py-2 text-sm text-[var(--text-muted)]">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="flex items-center gap-1 px-3.5 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:bg-white/[0.05] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
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
