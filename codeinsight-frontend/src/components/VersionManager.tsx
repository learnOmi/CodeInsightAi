"use client";

import { useState } from "react";
import { useVersions, useSwitchVersion, useRollbackVersion } from "@/hooks/use-repositories";
import { StatusBadge } from "@/components/analysis-status";
import type { components } from "@codeinsight/shared";

type AnalysisVersion = components["schemas"]["AnalysisVersion"];

interface VersionManagerProps {
  repositoryId: string;
}

export function VersionManager({ repositoryId }: VersionManagerProps) {
  const { data: versions, isLoading } = useVersions(repositoryId);
  const switchVersion = useSwitchVersion();
  const rollbackVersion = useRollbackVersion();
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false);
  const [error, setError] = useState("");

  const handleSwitch = async (version: string) => {
    setError("");
    try {
      await switchVersion.mutateAsync({ repositoryId, version });
    } catch (_err) {
      setError("切换版本失败，请重试");
    }
  };

  const handleRollback = async () => {
    if (!selectedVersion) return;
    setError("");
    try {
      await rollbackVersion.mutateAsync({ repositoryId, version: selectedVersion });
      setShowRollbackConfirm(false);
      setSelectedVersion(null);
    } catch (_err) {
      setError("回滚版本失败，请重试");
    }
  };

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString("zh-CN");
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[var(--primary)]"></div>
      </div>
    );
  }

  if (!versions || versions.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--text-muted)]">
        暂无分析版本
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-red-600 text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)]">
              <th className="text-left py-3 px-4 font-medium text-[var(--text-secondary)]">版本号</th>
              <th className="text-left py-3 px-4 font-medium text-[var(--text-secondary)]">状态</th>
              <th className="text-left py-3 px-4 font-medium text-[var(--text-secondary)]">文件数</th>
              <th className="text-left py-3 px-4 font-medium text-[var(--text-secondary)]">知识点数</th>
              <th className="text-left py-3 px-4 font-medium text-[var(--text-secondary)]">创建时间</th>
              <th className="text-left py-3 px-4 font-medium text-[var(--text-secondary)]">操作</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((version: AnalysisVersion) => (
              <tr
                key={version.version}
                className={`border-b border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors ${
                  version.isCurrent ? "bg-[var(--bg-active)]" : ""
                }`}
              >
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[var(--text-primary)]">{version.version}</span>
                    {version.isCurrent && (
                      <span className="text-xs bg-[var(--primary)] text-white px-2 py-0.5 rounded-full">
                        当前
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <StatusBadge status={version.status} />
                </td>
                <td className="py-3 px-4 text-[var(--text-secondary)]">
                  {version.analyzedFiles}/{version.totalFiles}
                </td>
                <td className="py-3 px-4 text-[var(--text-secondary)]">
                  {version.knowledgePointsCount}
                </td>
                <td className="py-3 px-4 text-[var(--text-secondary)]">
                  {formatDate(version.createdAt)}
                </td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    {!version.isCurrent && version.status === "completed" && (
                      <button
                        onClick={() => handleSwitch(version.version)}
                        disabled={switchVersion.isPending}
                        className="px-3 py-1 text-xs bg-[var(--primary)] text-white rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
                      >
                        切换
                      </button>
                    )}
                    {!version.isCurrent && version.status === "completed" && (
                      <button
                        onClick={() => {
                          setSelectedVersion(version.version);
                          setShowRollbackConfirm(true);
                        }}
                        disabled={rollbackVersion.isPending}
                        className="px-3 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600 disabled:opacity-50 transition-colors"
                      >
                        回滚
                      </button>
                    )}
                    {version.isCurrent && (
                      <span className="text-xs text-[var(--text-muted)]">当前版本</span>
                    )}
                    {version.status !== "completed" && !version.isCurrent && (
                      <span className="text-xs text-[var(--text-muted)]">暂不可用</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showRollbackConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--bg-card)] rounded-lg shadow-xl p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">确认回滚</h3>
            <p className="text-[var(--text-secondary)] mb-4">
              确定要将仓库回滚到版本 <code className="font-mono">{selectedVersion}</code> 吗？
              此操作将恢复该版本的所有数据。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowRollbackConfirm(false);
                  setSelectedVersion(null);
                }}
                className="flex-1 px-4 py-2 text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] rounded transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleRollback}
                disabled={rollbackVersion.isPending}
                className="flex-1 px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {rollbackVersion.isPending ? "回滚中..." : "确认回滚"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}