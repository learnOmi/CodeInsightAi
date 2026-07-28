"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiFetch } from "@/api/base";
import type { components } from "@codeinsight/shared";

// Backend returns agentStatus alongside standard fields; the shared
// package's generated types were not regenerated after this field was added.
type AnalysisVersionWithStatus = components["schemas"]["AnalysisVersion"] & {
  agentStatus?: Record<string, AgentStatusInfo>;
};

interface AgentStatusPanelProps {
  versions: AnalysisVersionWithStatus[];
  repositoryId: string;
  onStatusChange: () => void;
}

// 后端 agent_status 使用分类代码 (DP/AD/AL/ET/DK/TT/TK)
const CATEGORY_NAMES: Record<string, string> = {
  DP: "设计模式",
  AD: "架构设计",
  AL: "算法实现",
  ET: "工程技术",
  DK: "领域知识",
  TT: "开发模板",
  TK: "技术栈",
};

interface AgentStatusInfo {
  status: string;
  knowledge_points_count?: number;
  error?: string;
  attempts?: number;
  timestamp?: string;
  total_failed?: number;
}

export function AgentStatusPanel({ versions, repositoryId, onStatusChange }: AgentStatusPanelProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);

  // 获取最新完成版本的 agent_status
  const latestVersion = versions.find(
    (v) => v.status === "completed" && v.isCurrent
  ) || versions.find((v) => v.status === "completed");

  if (!latestVersion) {
    return null;
  }

  const agentStatus = (latestVersion as { agentStatus?: Record<string, AgentStatusInfo> }).agentStatus;
  if (!agentStatus || Object.keys(agentStatus).length === 0) {
    return null;
  }

  const categoryKeys = Object.keys(agentStatus).filter((key) => key !== "_expansion");
  const failedCategories = categoryKeys.filter((key) => agentStatus[key].status === "failed");
  const successCategories = categoryKeys.filter((key) => agentStatus[key].status === "success");
  const retryingCategories = categoryKeys.filter((key) => agentStatus[key].status === "retrying");

  // 检查拓展内容生成状态
  const expansionStatus = agentStatus["_expansion"];
  const hasExpansionFailure = expansionStatus && expansionStatus.status === "partial_failure";

  const handleRetry = async (category: string) => {
    if (retrying === category) return;
    setRetrying(category);
    try {
      await apiFetch<{ status: string; task_id?: string; message: string }>(
        `/api/v1/retry/${repositoryId}/${category}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ force: true }),
        }
      );
      onStatusChange();
    } catch (err) {
      console.error(`重试 ${category} 失败:`, err);
    } finally {
      setRetrying(null);
    }
  };

  const handleExpansionRetry = async () => {
    if (retrying === "_expansion") return;
    setRetrying("_expansion");
    try {
      await apiFetch<{ status: string; task_id?: string; message: string }>(
        `/api/v1/retry/${repositoryId}/expansion`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        }
      );
      onStatusChange();
    } catch (err) {
      console.error("重试拓展内容失败:", err);
    } finally {
      setRetrying(null);
    }
  };

  return (
    <div className="mt-4 pt-4 border-t border-[var(--border)]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left text-sm font-medium text-[var(--text-primary)] hover:text-brand transition-colors flex justify-between items-center"
      >
        <span>{t("agentStatus.header", { version: latestVersion.version })}</span>
        <span>{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {/* 摘要行 */}
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] flex-wrap">
            {successCategories.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="text-green-500">✓</span>
                {t("agentStatus.success", { n: successCategories.length })}
              </span>
            )}
            {failedCategories.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="text-status-error">✗</span>
                {t("agentStatus.failed", { n: failedCategories.length })}
              </span>
            )}
            {retryingCategories.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="text-brand">⟳</span>
                {t("agentStatus.retrying", { n: retryingCategories.length })}
              </span>
            )}
          </div>

          {/* 详细列表 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {categoryKeys.map((categoryCode) => {
              const status = agentStatus[categoryCode];
              const displayName = t(`agentStatus.categories.${categoryCode}`) || CATEGORY_NAMES[categoryCode] || categoryCode;
              const isFailed = status.status === "failed";
              const isRetrying = status.status === "retrying";

              return (
                <div
                  key={categoryCode}
                  className={`p-2 rounded text-sm flex justify-between items-center ${
                    isFailed
                      ? "bg-status-error/10 text-status-error"
                      : isRetrying
                      ? "bg-brand/10 text-brand"
                      : "bg-green-50/30 text-green-700"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span>{displayName}</span>
                    {isRetrying && <span className="text-xs">{t("agentStatus.retryingLabel")}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs">
                      {isFailed
                        ? t("agentStatus.failedLabel")
                        : status.status === "retrying"
                        ? t("agentStatus.retryLabel")
                        : t("agentStatus.countLabel", { n: status.knowledge_points_count || 0 })}
                    </span>
                    {isFailed && (
                      <button
                        onClick={() => handleRetry(categoryCode)}
                        disabled={retrying === categoryCode}
                        className="px-2 py-0.5 text-[10px] bg-status-warning text-white rounded hover:opacity-90 disabled:opacity-50 transition-opacity font-medium"
                      >
                        {retrying === categoryCode ? "..." : t("agentStatus.retryBtn")}
                      </button>
                    )}
                    {!isFailed && (
                      <button
                        onClick={() => handleRetry(categoryCode)}
                        disabled={retrying === categoryCode}
                        className="px-2 py-0.5 text-[10px] border border-[var(--border)] text-[var(--text-secondary)] rounded hover:bg-[var(--bg-hover)] disabled:opacity-50 transition-colors"
                      >
                        {retrying === categoryCode ? "..." : t("agentStatus.rerunBtn")}
                      </button>
                    )}
                  </div>
                  {isFailed && status.error && (
                    <div className="text-xs mt-1 opacity-80 w-full truncate">
                      {t("agentStatus.errorPrefix")} {status.error}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* 批量重试按钮 - 仅显示有失败的项 */}
          {failedCategories.length > 1 && (
            <button
              onClick={async () => {
                setRetrying("__batch__");
                try {
                  await apiFetch(`/api/v1/retry/${repositoryId}/batch`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ categories: failedCategories, force: true }),
                  });
                  onStatusChange();
                } catch (err) {
                  console.error("批量重试失败:", err);
                } finally {
                  setRetrying(null);
                }
              }}
              className="mt-3 w-full px-3 py-2 text-xs font-medium bg-status-warning text-white rounded hover:opacity-90 shadow-sm disabled:opacity-50 transition-opacity"
            >
              {t("agentStatus.batchRetry", { n: failedCategories.length })}
            </button>
          )}

          {/* 拓展内容重试按钮 */}
          {hasExpansionFailure && (
            <div className="mt-3 p-3 rounded bg-status-warning/10 border border-status-warning/30">
              <div className="text-xs text-[var(--text-primary)] mb-2">
                {t("agentStatus.expandFailBanner", { n: expansionStatus.total_failed || "?" })}
              </div>
              <button
                onClick={handleExpansionRetry}
                disabled={retrying === "_expansion"}
                className="w-full px-3 py-2 text-xs font-medium bg-status-warning text-white rounded hover:opacity-90 shadow-sm disabled:opacity-50 transition-opacity"
              >
                {retrying === "_expansion" ? t("agentStatus.retryingExpand") : t("agentStatus.retryExpandBtn")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
