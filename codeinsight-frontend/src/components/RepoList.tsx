"use client";

import { useState, useMemo } from "react";
import { useRepositories } from "@/hooks/use-repositories";
import { RepoCard } from "./RepoCard";
import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];
type RepositoryStatus = components["schemas"]["RepositoryStatus"];

const PAGE_SIZE = 30;

const filterOptions: { value: RepositoryStatus | "all"; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "pending", label: "待分析" },
  { value: "analyzing", label: "分析中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
];

export function RepoList() {
  const [filter, setFilter] = useState<RepositoryStatus | "all">("all");
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useRepositories(page, PAGE_SIZE);

  const filteredRepositories = useMemo(() => {
    if (!data?.items) return [];
    if (filter === "all") return data.items;
    return data.items.filter((repo: Repository) => repo.status === filter);
  }, [data, filter]);

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-brand border-t-transparent"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center text-status-error py-8">
        加载失败，请刷新重试
      </div>
    );
  }

  const totalPages = data?.totalPages || 1;
  const total = data?.total || 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {filterOptions.map((option) => (
            <button
              key={option.value}
              onClick={() => {
                setFilter(option.value);
                setPage(1);
              }}
              className={`rounded-md text-xs font-medium px-3 py-1.5 transition-colors ${
                filter === option.value
                  ? "bg-brand text-white"
                  : "border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-[var(--text-muted)]">
          共 {total} 个仓库
        </span>
      </div>

      {filteredRepositories.length === 0 ? (
        <div className="text-center py-12 text-[var(--text-muted)]">
          {filter === "all" ? "暂无仓库" : `暂无${filterOptions.find((o) => o.value === filter)?.label}的仓库`}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredRepositories.map((repo) => (
              <RepoCard key={repo.id} repository={repo} />
            ))}
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 pt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                上一页
              </button>
              {generatePageNumbers(page, totalPages).map((p, i) =>
                p === "..." ? (
                  <span key={`ellipsis-${i}`} className="px-2 text-[var(--text-muted)] text-xs">...</span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(p as number)}
                    className={`w-8 h-8 rounded-md text-xs font-medium transition-colors ${
                      page === p
                        ? "bg-brand text-white"
                        : "border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
                    }`}
                  >
                    {p}
                  </button>
                )
              )}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** 生成分页按钮列表（含省略号） */
function generatePageNumbers(current: number, total: number): (number | "..." )[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages: (number | "...")[] = [1];
  if (current > 3) pages.push("...");
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) pages.push(i);
  if (current < total - 2) pages.push("...");
  pages.push(total);
  return pages;
}