"use client";

import { useState, type FormEvent } from "react";
import { useCreateRepository } from "@/hooks/use-repositories";
import { APIError } from "@/api/base";
import { cn } from "@/utils";

interface RepoFormProps {
  onClose?: () => void;
}

export function RepoForm({ onClose }: RepoFormProps) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const createRepository = useCreateRepository();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!name.trim()) {
      setError("请输入仓库名称");
      return;
    }
    if (!path.trim()) {
      setError("请输入仓库路径");
      return;
    }

    try {
      await createRepository.mutateAsync({
        name: name.trim(),
        path: path.trim(),
        autoAnalyze,
      });
      setSuccess("仓库创建成功");
      setName("");
      setPath("");
      setAutoAnalyze(true);
      setTimeout(() => {
        setSuccess("");
        onClose?.();
      }, 2000);
    } catch (err) {
      if (err instanceof APIError) {
        if (err.status === 409) {
          setError("该路径已存在仓库");
        } else {
          setError(err.message);
        }
      } else {
        setError("创建失败，请重试");
      }
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-xl font-semibold mb-4">添加仓库</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            仓库名称
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="例如：my-project"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            仓库路径
          </label>
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="例如：/path/to/repo"
          />
        </div>
        <div className="flex items-center">
          <input
            type="checkbox"
            id="auto-analyze"
            checked={autoAnalyze}
            onChange={(e) => setAutoAnalyze(e.target.checked)}
            className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
          />
          <label htmlFor="auto-analyze" className="ml-2 text-sm text-gray-700">
            创建后自动分析
          </label>
        </div>
        {error && (
          <div className="text-red-600 text-sm">{error}</div>
        )}
        {success && (
          <div className="text-green-600 text-sm">{success}</div>
        )}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={createRepository.isPending}
            className={cn(
              "flex-1 px-4 py-2 rounded-lg font-medium transition-colors",
              createRepository.isPending
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-blue-600 text-white hover:bg-blue-700"
            )}
          >
            {createRepository.isPending ? "创建中..." : "创建"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 rounded-lg font-medium text-gray-700 hover:bg-gray-50"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}