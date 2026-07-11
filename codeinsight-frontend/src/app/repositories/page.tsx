"use client";

import { useState } from "react";
import { RepoForm } from "@/components/RepoForm";
import { RepoList } from "@/components/RepoList";

export default function RepositoriesPage() {
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="min-h-screen bg-gray-100 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">仓库管理</h1>
            <p className="text-gray-600 mt-1">管理代码仓库并进行智能分析</p>
          </div>
          <button
            onClick={() => setShowForm(true)}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
          >
            添加仓库
          </button>
        </div>

        {showForm ? (
          <div className="max-w-md mx-auto mb-8">
            <RepoForm onClose={() => setShowForm(false)} />
          </div>
        ) : null}

        <RepoList />
      </div>
    </div>
  );
}