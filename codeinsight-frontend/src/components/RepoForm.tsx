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
  const [history, setHistory] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const createRepository = useCreateRepository();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

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
      savePathHistory(path.trim());
      onClose?.();
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
      // Chrome/Edge 在 webkitdirectory 模式下提供非标准 file.path 属性
      const absolutePath = (file as File & { path?: string }).path;
      if (absolutePath) {
        // 去掉文件名，保留目录的绝对路径
        const dirPath = absolutePath.replace(/[/\\][^/\\]*$/, "");
        setPath(dirPath);
        setError("");
      } else {
        // file.path 不可用（Chrome 86+ 已移除），降级为 webkitRelativePath
        // 这是相对路径，无法获取完整绝对路径，仅作为文件夹名提示
        const rawPath = file.webkitRelativePath;
        const parts = rawPath.split("/");
        // 如果有多级路径（如 "directives/index.js"），第一段是选中文件夹下的子目录名
        const hint = parts.length > 1 ? parts[0] : rawPath;
        setPath(hint);
        setError("⚠ 浏览器未提供完整路径，请手动补充绝对路径前缀");
      }
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
    <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5 shadow-sm">
      <h2 className="text-lg font-semibold mb-4 tracking-tight text-[var(--text-primary)]">添加仓库</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            仓库名称
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3.5 py-2 border border-[var(--border)] rounded-md text-sm bg-[var(--bg-base)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand transition-all placeholder:text-[var(--text-muted)]"
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
              className="w-full px-3.5 py-2 border border-[var(--border)] rounded-md text-sm bg-[var(--bg-base)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand transition-all placeholder:text-[var(--text-muted)]"
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
              className="px-3 py-2 bg-[var(--bg-hover)] border border-[var(--border)] rounded-md hover:bg-[var(--border)] transition-colors"
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
                  className="text-xs px-2 py-0.5 bg-brand/10 text-brand rounded hover:bg-brand/20 transition-colors"
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
            className="w-4 h-4 text-brand border-[var(--border)] rounded focus:ring-brand/50"
          />
          <label htmlFor="auto-analyze" className="ml-2 text-sm text-[var(--text-secondary)]">
            创建后自动分析
          </label>
        </div>
        {error && (
          <div className="text-status-error text-sm">{error}</div>
        )}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={createRepository.isPending}
            className={cn(
              "flex-1 px-3.5 py-2 text-sm rounded-md font-medium transition-colors",
              createRepository.isPending
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-brand text-white hover:opacity-90 shadow-sm"
            )}
          >
            {createRepository.isPending ? "创建中..." : "创建"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-2 text-sm border border-[var(--border)] rounded-md font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}