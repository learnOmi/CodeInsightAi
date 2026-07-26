"use client";

import { useState } from "react";
import type { components } from "@codeinsight/shared";

type AnalysisVersion = components["schemas"]["AnalysisVersion"];
type TaskStatus = components["schemas"]["TaskStatus"];

interface AgentStatusPanelProps {
  versions: AnalysisVersion[];
  onRetry: (agents: string[]) => void;
}

const taskNameMap: Record<string, string> = {
  design_pattern: "设计模式",
  architecture: "架构设计",
  algorithm: "算法实现",
  engineering: "工程技术",
  domain_knowledge: "领域知识",
  template_technique: "开发模板",
  technology_stack: "技术栈",
};

export function AgentStatusPanel({ versions, onRetry }: AgentStatusPanelProps) {
  const [expanded, setExpanded] = useState(false);

  // 获取最新完成版本的 agent_status
  const latestCompleted = versions.find(
    (v) => v.status === "completed" && v.isCurrent
  ) || versions.find((v) => v.status === "completed");

  if (!latestCompleted || !latestCompleted.agentStatus) {
    return null;
  }

  const agentStatus = latestCompleted.agentStatus as Record<string, { status: "success" | "failed"; count?: number; error?: string }>;
  const agentKeys = Object.keys(agentStatus);
  const failedAgents = agentKeys.filter((key) => agentStatus[key].status === "failed");
  const successAgents = agentKeys.filter((key) => agentStatus[key].status === "success");

  if (agentKeys.length === 0) return null;

  return (
    <div className="mt-4 pt-4 border-t border-[var(--border)]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left text-sm font-medium text-[var(--text-primary]) hover:text-brand transition-colors flex justify-between items-center"
      >
        <span>分析状态</span>
        <span>{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {/* 摘要行 */}
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            {successAgents.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="text-green-500">✓</span>
                {successAgents.length} 个维度成功
              </span>
            )}
            {failedAgents.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <span className="text-status-error">✗</span>
                {failedAgents.length} 个维度失败（点击重试）
              </span>
            )}
          </div>

          {/* 详细列表 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {agentKeys.map((agentKey) => {
              const status = agentStatus[agentKey];
              const displayName = taskNameMap[agentKey] || agentKey;
              const isFailed = status.status === "failed";

              return (
                <div
                  key={agentKey}
                  className={`p-2 rounded text-sm ${
                    isFailed
                      ? "bg-status-error/10 text-status-error"
                      : "bg-green-50/30 text-green-700"
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span>{displayName}</span>
                    <span className="font-mono text-xs">
                      {isFailed ? "失败" : `成功 (${status.count || 0})`}
                    </span>
                  </div>
                  {!isFailed && status.error && (
                    <div className="text-xs mt-1 opacity-80">错误: {status.error}</div>
                  )}
                </div>
              );
            })}
          </div>

          {/* 重试按钮 - 仅显示有失败的项 */}
          {failedAgents.length > 0 && (
            <button
              onClick={() => onRetry(failedAgents)}
              className="mt-3 w-full px-3 py-2 text-xs font-medium bg-status-warning text-white rounded hover:opacity-90 shadow-sm"
            >
              重试失败的维度 ({failedAgents.length})
            </button>
          )}
        </div>
      )}
    </div>
  );
}