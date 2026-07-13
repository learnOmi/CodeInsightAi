"use client";

import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { RepoForm } from "@/components/RepoForm";
import { RepoList } from "@/components/RepoList";

export default function RepositoriesPage() {
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="min-h-screen bg-[var(--bg-base)] py-8">
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

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-12">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-[var(--text-primary)]">仓库管理</h1>
            <p className="text-[var(--text-secondary)] mt-1">管理代码仓库并进行智能分析</p>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            添加仓库
          </button>
        </div>

        <RepoList />

        {/* 弹窗遮罩 */}
        {showForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-[var(--bg-card)] rounded-xl shadow-2xl w-full max-w-md mx-4">
              <RepoForm onClose={() => setShowForm(false)} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}