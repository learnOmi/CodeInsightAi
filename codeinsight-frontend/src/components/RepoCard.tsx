"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import {
  useSubmitAnalysis,
  useCancelTask,
  useDeleteRepository,
} from "@/hooks/use-repositories";
import { useSSE } from "@/hooks/use-sse";
import { APIError } from "@/api/base";
import { cn } from "@/utils";
import { getAnalysisStatusConfig } from "@codeinsight/shared";
import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];
type TaskStatus = components["schemas"]["TaskStatus"];

interface RepoCardProps {
  repository: Repository;
}

const taskStepLabels: Record<TaskStatus, string> = {
  pending: "等待中",
  scanning: "扫描文件",
  parsing: "解析代码",
  analyzing_structures: "结构分析",
  analyzing_modules: "AI 分析",
  storing: "存储结果",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export function RepoCard({ repository }: RepoCardProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [cancelError, setCancelError] = useState("");
  const [currentTaskId, setCurrentTaskId] = useState<string>("");

  const queryClient = useQueryClient();
  const submitAnalysis = useSubmitAnalysis();
  const cancelTask = useCancelTask();
  const deleteRepository = useDeleteRepository();

  // 从 localStorage 读取 pending taskId（创建仓库时自动分析场景）
  // 使用 initialized flag 确保组件挂载时立即检查，不依赖 repository.currentTaskId 变化
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!initialized) {
      const pendingTaskId = localStorage.getItem("pending_task_id");
      if (pendingTaskId) {
        setCurrentTaskId(pendingTaskId);
        localStorage.removeItem("pending_task_id");
      }
      setInitialized(true);
    }
  }, [initialized]);

  const isAnalyzing = repository.status === "analyzing";
  const taskId = currentTaskId || repository.currentTaskId || "";

  console.log("[RepoCard] isAnalyzing:", isAnalyzing, "currentTaskId:", currentTaskId, "repository.currentTaskId:", repository.currentTaskId, "taskId:", taskId);

  // SSE 实时进度：只要存在 taskId 就连接，不依赖 isAnalyzing 状态
  // （isAnalyzing 依赖仓库列表 refetch，而分析期间没有 refetchInterval，导致状态卡顿）
  const { data: sseData, error: sseError, isComplete } = useSSE(
    taskId,
    !!taskId,
  );

  // SSE 连接完成/失败时刷新仓库数据，并清除 currentTaskId 避免重连
  useEffect(() => {
    if (isComplete) {
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
      // 清除 currentTaskId，断开 SSE，等待下次分析重新建立连接
      setCurrentTaskId("");
    }
  }, [isComplete, queryClient]);

  const handleSubmitAnalysis = async () => {
    setSubmitError("");
    console.log("[RepoCard] 提交前 - currentTaskId:", currentTaskId, "repository.currentTaskId:", repository.currentTaskId);
    try {
      const result = await submitAnalysis.mutateAsync({ repositoryId: repository.id });
      console.log("[RepoCard] submitAnalysis result:", result);
      console.log("[RepoCard] 提交后 - result.status:", result.status);
      // 立即刷新仓库列表，使 status 从 cancelled 更新为 analyzing
      queryClient.invalidateQueries({ queryKey: ["repositories"] });
      // Eager 模式下分析同步完成，直接刷新仓库列表显示最终状态
      if (result.status === "completed" || result.status === "failed") {
        console.log("[RepoCard] status 是 completed/failed，不设置 taskId");
      } else {
        console.log("[RepoCard] 设置 currentTaskId:", result.taskId);
        setCurrentTaskId(result.taskId);
      }
    } catch (err) {
      if (err instanceof APIError) {
        if (err.status === 409) {
          setSubmitError("已有分析任务正在进行");
        } else if (err.status === 304) {
          setSubmitError("代码内容未变化，无需重复分析");
        } else {
          setSubmitError(err.message);
        }
      } else {
        setSubmitError("提交失败，请重试");
      }
    }
  };

  const handleCancelTask = async () => {
    setCancelError("");
    if (taskId) {
      try {
        await cancelTask.mutateAsync(taskId);
        // 立即清除 taskId 断开 SSE 连接，避免按钮状态卡死
        setCurrentTaskId("");
        queryClient.invalidateQueries({ queryKey: ["repositories"] });
      } catch (err) {
        if (err instanceof APIError) {
          setCancelError(err.message);
        } else {
          setCancelError("取消失败，请重试");
        }
      }
    }
  };

  const handleDelete = async () => {
    setDeleteError("");
    try {
      await deleteRepository.mutateAsync(repository.id);
      setShowConfirm(false);
    } catch (err) {
      if (err instanceof APIError) {
        setDeleteError(`删除失败: ${err.message}`);
      } else {
        setDeleteError("删除失败，请重试");
      }
    }
  };

  const statusConfig = getAnalysisStatusConfig(repository.status);
  const progress = sseData?.progress || { percent: 0, filesProcessed: 0, filesTotal: 0, currentStep: "pending" as TaskStatus, knowledgePointsFound: 0, totalLines: 0 };
  const currentStep = progress.currentStep ? taskStepLabels[progress.currentStep] : "";
  // 进度条显示条件：有 taskId 且 SSE 未完成
  // （isAnalyzing 依赖仓库列表 refetch，分析期间无 refetchInterval，导致状态卡顿）
  const showProgress = !!taskId && !isComplete;

  // 检查部分失败：如果状态是 completed 但有 incomplete agent results（通过 error_message 或其他方式指示）
  const isPartialFailure = repository.status === "completed" && repository.errorMessage;

  return (
    <div className="group relative rounded-2xl overflow-hidden bg-[var(--bg-card)] transition-all duration-500 hover:-translate-y-1 hover:shadow-[var(--glow-brand-light)]">
      {isPartialFailure && (
        <div className="absolute top-0 right-0 z-10">
          <div className="bg-status-warning/90 text-status-warning px-3 py-1 text-xs font-medium rounded-bl-full">
            ⚠️ AI 分析部分完成
          </div>
        </div>
      )}
      {/* 渐变边框层 — hover 时显现 */}
      <div className="absolute inset-0 rounded-2xl bg-gradient-to-b from-brand/20 via-brand/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      {/* 顶部光条 */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

      {/* 内容层 */}
      <div className="relative m-[1px] rounded-2xl bg-[var(--bg-card)] p-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <Link
              href={`/repositories/${repository.id}/files`}
              className="text-[var(--text-primary)] hover:text-brand transition-colors"
            >
              <h3 className="text-lg font-semibold">{repository.name}</h3>
            </Link>
            <p className="text-[11px] text-[var(--text-muted)] font-mono truncate max-w-xs mt-0.5 opacity-70">{repository.path}</p>
          </div>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold tracking-wide",
              statusConfig.color,
              statusConfig.animate && "animate-pulse"
            )}
          >
            <span className={`w-1.5 h-1.5 rounded-full`} style={{ backgroundColor: "currentColor" }} />
            {statusConfig.label}
          </span>
        </div>

        {showProgress && (
          <div className="mb-4 space-y-1.5">
            <div className="flex justify-between text-[11px]">
              <span className="text-[var(--text-muted)]">{currentStep || "分析中"}</span>
              <span className="font-mono tabular-nums text-[var(--text-muted)]">{progress.percent}%</span>
            </div>
            <div className="w-full bg-[var(--bg-hover)] rounded-full h-1 overflow-hidden">
              <div
                className="bg-gradient-to-r from-brand to-brand-fg h-1 rounded-full transition-all duration-300"
                style={{ width: `${progress.percent}%` }}
              />
            </div>
            <div className="text-[11px] text-[var(--text-muted)]">
              {progress.filesProcessed} / {progress.filesTotal} 文件
            </div>
          </div>
        )}

        <div className="grid grid-cols-3 gap-4 mb-5 divide-x divide-[var(--border)]/50">
          <StatItem value={showProgress ? progress.filesTotal || repository.fileCount : repository.fileCount} label="FILES" />
          <StatItem value={showProgress ? progress.totalLines || repository.lineCount : repository.lineCount} label="LINES" />
          <StatItem value={showProgress ? progress.knowledgePointsFound || repository.knowledgePointsCount : repository.knowledgePointsCount} label="INSIGHTS" />
        </div>

        {submitError && (
            <div className="bg-status-error/10 text-status-error rounded-md px-3 py-2 text-xs mb-3">{submitError}</div>
          )}
          {sseError && (
            <div className="bg-status-error/10 text-status-error rounded-md px-3 py-2 text-xs mb-3">{sseError}</div>
          )}
          {cancelError && (
            <div className="bg-status-error/10 text-status-error rounded-md px-3 py-2 text-xs mb-3">{cancelError}</div>
          )}
          {deleteError && (
          <div className="bg-status-error/10 text-status-error rounded-md px-3 py-2 text-xs mb-3">{deleteError}</div>
        )}

        <div className="flex gap-2">
          {!showProgress && (
            <Link
              href={`/repositories/${repository.id}/files`}
              className="flex-1 px-3 py-2 rounded-md text-xs font-medium text-center transition-colors bg-[var(--bg-hover)] text-[var(--text-primary)] hover:bg-[var(--border)]"
            >
              文件
            </Link>
          )}
          {!showProgress && (
            <button
              onClick={handleSubmitAnalysis}
              disabled={submitAnalysis.isPending}
              className={cn(
                "flex-1 px-3 py-2 rounded-md text-xs font-medium transition-colors",
                submitAnalysis.isPending
                  ? "bg-brand/60 cursor-not-allowed text-white/80"
                  : "bg-brand text-white hover:opacity-90 shadow-sm"
              )}
            >
              {submitAnalysis.isPending ? "提交中..." : "开始分析"}
            </button>
          )}
          {showProgress && (
            <button
              onClick={handleCancelTask}
              disabled={cancelTask.isPending}
              className={cn(
                "flex-1 px-4 py-2 rounded-md text-xs font-medium transition-colors",
                cancelTask.isPending
                  ? "bg-brand/60 cursor-not-allowed text-white/80"
                  : "bg-status-warning text-white shadow-sm"
              )}
            >
              {cancelTask.isPending ? "取消中..." : "取消分析"}
            </button>
          )}
          {showConfirm ? (
            <>
              <button
                onClick={handleDelete}
                disabled={deleteRepository.isPending}
                className={cn(
                  "flex-1 px-4 py-2 rounded-md text-xs font-medium transition-colors",
                  deleteRepository.isPending
                    ? "bg-brand/60 cursor-not-allowed text-white/80"
                    : "text-status-error bg-status-error/10 hover:bg-status-error/20"
                )}
              >
                {deleteRepository.isPending ? "删除中..." : "确认删除"}
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className="px-4 py-2 border border-[var(--border)] rounded-md text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
              >
                取消
              </button>
            </>
          ) : (
            <button
              onClick={() => setShowConfirm(true)}
              className="px-4 py-2 border border-[var(--border)] rounded-md text-xs font-medium text-status-error/70 hover:bg-status-error/10 transition-colors"
            >
              删除
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** 统计项（数字 + 英文标签），用于 RepoCard 底部 */
function StatItem({ value, label }: { value: number; label: string }) {
  return (
    <div className="text-center">
      <div className="text-xl font-bold text-[var(--text-primary)] tabular-nums">{value}</div>
      <div className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">{label}</div>
    </div>
  );
}