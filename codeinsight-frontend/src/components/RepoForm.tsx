"use client";

import { useState, useRef, type FormEvent, type ChangeEvent } from "react";
import { useCreateRepository } from "@/hooks/use-repositories";
import { APIError } from "@/api/base";
import { cn } from "@/utils";

const HISTORY_KEY = "repo_path_history";
const MAX_HISTORY = 5;

function loadPathHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function savePathHistory(path: string): void {
  try {
    const history = loadPathHistory().filter((p) => p !== path);
    history.unshift(path);
    if (history.length > MAX_HISTORY) history.pop();
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
  } catch {
    // ignore
  }
}

interface RepoFormProps {
  onClose?: () => void;
}

export function RepoForm({ onClose }: RepoFormProps) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
      savePathHistory(path.trim());
      setHistory(loadPathHistory());
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

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      // webkitdirectory 模式下，file.path 在部分浏览器不可用，
      // 使用 file.webkitRelativePath 作为路径（去掉最外层文件夹名）
      const rawPath = file.webkitRelativePath;
      // 去掉最外层文件夹名（如 "my-project/src/index.ts" → "my-project"）
      const normalizedPath = rawPath.split("/")[0];
      setPath(normalizedPath);
      // 清空 input value 以便下次重复选择同一目录也能触发 onChange
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleClearHistory = () => {
    localStorage.removeItem(HISTORY_KEY);
    setHistory([]);
  };

  return (
    <div className="bg-[var(--bg-card)] rounded-lg shadow-md p-6">
      <h2 className="text-xl font-semibold mb-4 text-[var(--text-primary)]">添加仓库</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            仓库名称
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-4 py-2 border border-[var(--border)] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-[var(--bg-base)] text-[var(--text-primary)]"
            placeholder="例如：my-project"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            仓库路径
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              className="w-full px-4 py-2 border border-[var(--border)] rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-[var(--bg-base)] text-[var(--text-primary)]"
              placeholder="例如：/path/to/repo"
            />
            <input
              ref={fileInputRef}
              type="file"
              // @ts-expect-error webkitdirectory is a non-standard but widely supported attribute
              webkitdirectory=""
              className="hidden"
              onChange={handleFileSelect}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-3 py-2 bg-[var(--bg-hover)] border border-[var(--border)] rounded-lg hover:bg-[var(--border)] transition-colors"
              title="选择本地目录"
            >
              📁
            </button>
          </div>
          {history.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {history.map((h, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setPath(h)}
                  className="text-xs px-2 py-0.5 bg-blue-50 text-blue-600 rounded hover:bg-blue-100"
                >
                  {h}
                </button>
              ))}
              <button
                type="button"
                onClick={handleClearHistory}
                className="text-xs px-2 py-0.5 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                清空
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center">
          <input
            type="checkbox"
            id="auto-analyze"
            checked={autoAnalyze}
            onChange={(e) => setAutoAnalyze(e.target.checked)}
            className="w-4 h-4 text-blue-600 border-[var(--border)] rounded focus:ring-blue-500"
          />
          <label htmlFor="auto-analyze" className="ml-2 text-sm text-[var(--text-secondary)]">
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
            className="px-4 py-2 border border-[var(--border)] rounded-lg font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}