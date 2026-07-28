"use client";

import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useRepositories } from "@/hooks/use-repositories";
import { RepoCard } from "./RepoCard";
import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];
type RepositoryStatus = components["schemas"]["RepositoryStatus"];

const PAGE_SIZE = 30;

export function RepoList() {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<RepositoryStatus | "all">("all");
  const [page, setPage] = useState(1);

  const filterOptions: { value: RepositoryStatus | "all"; label: string }[] = [
    { value: "all", label: t("repoList.filter.all") },
    { value: "pending", label: t("repoList.filter.pending") },
    { value: "analyzing", label: t("repoList.filter.analyzing") },
    { value: "completed", label: t("repoList.filter.done") },
    { value: "failed", label: t("repoList.filter.failed") },
    { value: "cancelled", label: t("repoList.filter.cancelled") },
  ];

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
        {t("repoList.loadError")}
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
          {t("repoList.count", { n: total })}
        </span>
      </div>

      {filteredRepositories.length === 0 ? (
        <div className="text-center py-12 text-[var(--text-muted)]">
          {filter === "all"
            ? t("repoList.empty")
            : t("repoList.emptyFilter", {
                label: filterOptions.find((o) => o.value === filter)?.label,
              })}
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
                {t("repoList.prevPage")}
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
                {t("repoList.nextPage")}
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