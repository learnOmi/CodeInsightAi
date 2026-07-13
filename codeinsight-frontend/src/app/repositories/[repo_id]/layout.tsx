"use client";

import { use, type ReactNode } from "react";
import Link from "next/link";
import { useRepository } from "@/hooks/use-repositories";
import { useAnalysisStatus } from "@/hooks/use-analysis-status";
import { StatusBadge } from "@/components/analysis-status";

/** 仓库详情页布局（顶部导航栏 + 内容区域） */
export default function RepoDetailLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ repo_id: string }>;
}) {
  const { repo_id } = use(params);
  const { data: repo } = useRepository(repo_id);
  const { data: statusRepo } = useAnalysisStatus(repo_id);

  const currentStatus = statusRepo?.status ?? repo?.status ?? "pending";

  return (
    <main className="min-h-screen bg-gray-50">
      {/* 顶部导航栏 */}
      <header className="sticky top-0 z-10 border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <Link
            href="/repositories"
            className="text-sm text-gray-500 hover:text-gray-800 transition-colors"
          >
            {"\u2190 仓库列表"}
          </Link>
          <div className="h-5 w-px bg-gray-200" />
          <h1 className="text-base font-semibold text-gray-900">
            {repo?.name ?? "\u52A0\u8F7D\u4E2D..."}
          </h1>
          {repo && (
            <span className="text-xs text-gray-400 truncate max-w-xs">
              {repo.path}
            </span>
          )}
          <div className="ml-auto">
            <StatusBadge status={currentStatus} />
          </div>
        </div>
      </header>

      {/* 主体内容 */}
      <div className="mx-auto max-w-7xl px-4 py-6">
        {children}
      </div>
    </main>
  );
}
