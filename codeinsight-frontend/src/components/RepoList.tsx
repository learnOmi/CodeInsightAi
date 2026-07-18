"use client";

import { useState } from "react";
import { useRepositories } from "@/hooks/use-repositories";
import { RepoCard } from "./RepoCard";
import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];
type RepositoryStatus = components["schemas"]["RepositoryStatus"];

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

  const { data: repositories, isLoading, error } = useRepositories();

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

  const filteredRepositories = repositories?.filter((repo: Repository) => {
    if (filter === "all") return true;
    return repo.status === filter;
  }) || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {filterOptions.map((option) => (
          <button
            key={option.value}
            onClick={() => setFilter(option.value)}
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

      {filteredRepositories.length === 0 ? (
        <div className="text-center py-12 text-[var(--text-muted)]">
          {filter === "all" ? "暂无仓库" : `暂无${filterOptions.find((o) => o.value === filter)?.label}的仓库`}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredRepositories.map((repo) => (
            <RepoCard key={repo.id} repository={repo} />
          ))}
        </div>
      )}
    </div>
  );
}