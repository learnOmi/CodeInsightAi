"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import {
  useSubmitAnalysis,
  useCancelTask,
  useDeleteRepository,
  useTaskStatus,
} from "@/hooks/use-repositories";
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

  const isAnalyzing = repository.status === "analyzing";
  const taskId = currentTaskId;

  const { data: taskData } = useTaskStatus(
    isAnalyzing ? taskId : "",
    isAnalyzing
  ) as { data: components["schemas"]["AnalysisTask"] | undefined };

  const handleSubmitAnalysis = async () => {
    setSubmitError("");
    try {
      const result = await submitAnalysis.mutateAsync({ repositoryId: repository.id });
      // Eager 模式下分析同步完成，直接刷新仓库列表显示最终状态
      if (result.status === "completed" || result.status === "failed") {
        queryClient.invalidateQueries({ queryKey: ["repositories"] });
      } else {
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
    if (taskData?.taskId) {
      try {
        await cancelTask.mutateAsync(taskData.taskId);
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
  const progress = taskData?.progress || { percent: 0, filesProcessed: 0, filesTotal: 0, currentStep: "pending" as TaskStatus, knowledgePointsFound: 0 };
  const currentStep = progress.currentStep ? taskStepLabels[progress.currentStep] : "";

  return (
    <div className="group relative rounded-2xl overflow-hidden bg-[var(--bg-card)] transition-all duration-500 hover:-translate-y-1 hover:shadow-[var(--glow-brand-light)]">
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

        {isAnalyzing && (
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
          <StatItem value={repository.fileCount} label="FILES" />
          <StatItem value={repository.lineCount} label="LINES" />
          <StatItem value={repository.knowledgePointsCount} label="INSIGHTS" />
        </div>

        {submitError && (
            <div className="bg-status-error/10 text-status-error rounded-md px-3 py-2 text-xs mb-3">{submitError}</div>
          )}
          {cancelError && (
            <div className="bg-status-error/10 text-status-error rounded-md px-3 py-2 text-xs mb-3">{cancelError}</div>
          )}
          {deleteError && (
          <div className="bg-status-error/10 text-status-error rounded-md px-3 py-2 text-xs mb-3">{deleteError}</div>
        )}

        <div className="flex gap-2">
          {!isAnalyzing && (
            <Link
              href={`/repositories/${repository.id}/files`}
              className="flex-1 px-4 py-2 rounded-md text-xs font-medium text-center transition-colors bg-[var(--bg-hover)] text-[var(--text-primary)] hover:bg-[var(--border)]"
            >
              查看文件
            </Link>
          )}
          {!isAnalyzing && (
            <button
              onClick={handleSubmitAnalysis}
              disabled={submitAnalysis.isPending}
              className={cn(
                "flex-1 px-4 py-2 rounded-md text-xs font-medium transition-colors",
                submitAnalysis.isPending
                  ? "bg-brand/60 cursor-not-allowed text-white/80"
                  : "bg-brand text-white hover:opacity-90 shadow-sm"
              )}
            >
              {submitAnalysis.isPending ? "提交中..." : "开始分析"}
            </button>
          )}
          {isAnalyzing && (
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