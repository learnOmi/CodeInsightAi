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
    <div className="bg-[var(--bg-card)] rounded-lg shadow-md p-6 hover:shadow-lg transition-all duration-200 border border-[var(--border)]">
      <div className="flex justify-between items-start mb-4">
        <div>
          <Link
            href={`/repositories/${repository.id}/files`}
            className="text-[var(--text-primary)] hover:text-blue-500 transition-colors"
          >
            <h3 className="text-lg font-semibold">{repository.name}</h3>
          </Link>
          <p className="text-sm text-[var(--text-secondary)] truncate max-w-xs">{repository.path}</p>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium",
            statusConfig.color,
            statusConfig.animate && "animate-pulse"
          )}
        >
          <span className={statusConfig.animate ? "inline-block animate-spin" : ""}>
            {statusConfig.icon}
          </span>
          {statusConfig.label}
        </span>
      </div>

      {isAnalyzing && (
        <div className="mb-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-[var(--text-secondary)]">{currentStep || "分析中"}</span>
            <span className="text-[var(--text-secondary)]">{progress.percent}%</span>
          </div>
          <div className="w-full bg-[var(--bg-hover)] rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
          <div className="text-xs text-[var(--text-muted)]">
            {progress.filesProcessed} / {progress.filesTotal} 文件
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="text-center">
          <div className="text-xl font-bold text-[var(--text-primary)]">{repository.fileCount}</div>
          <div className="text-xs text-[var(--text-muted)]">文件数</div>
        </div>
        <div className="text-center">
          <div className="text-xl font-bold text-[var(--text-primary)]">{repository.lineCount}</div>
          <div className="text-xs text-[var(--text-muted)]">代码行数</div>
        </div>
        <div className="text-center">
          <div className="text-xl font-bold text-[var(--text-primary)]">{repository.knowledgePointsCount}</div>
          <div className="text-xs text-[var(--text-muted)]">知识点</div>
        </div>
      </div>

      {submitError && (
          <div className="text-red-600 text-sm mb-3">{submitError}</div>
        )}
        {cancelError && (
          <div className="text-red-600 text-sm mb-3">{cancelError}</div>
        )}
        {deleteError && (
        <div className="text-red-600 text-sm mb-3">{deleteError}</div>
      )}

      <div className="flex gap-2">
        {!isAnalyzing && (
          <Link
            href={`/repositories/${repository.id}/files`}
            className="flex-1 px-4 py-2 rounded-lg font-medium text-sm text-center transition-colors bg-[var(--bg-hover)] text-[var(--text-primary)] hover:bg-[var(--border)]"
          >
            查看文件
          </Link>
        )}
        {!isAnalyzing && (
          <button
            onClick={handleSubmitAnalysis}
            disabled={submitAnalysis.isPending}
            className={cn(
              "flex-1 px-4 py-2 rounded-lg font-medium text-sm transition-colors",
              submitAnalysis.isPending
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-blue-600 text-white hover:bg-blue-700"
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
              "flex-1 px-4 py-2 rounded-lg font-medium text-sm transition-colors",
              cancelTask.isPending
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-yellow-600 text-white hover:bg-yellow-700"
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
                "flex-1 px-4 py-2 rounded-lg font-medium text-sm transition-colors",
                deleteRepository.isPending
                  ? "bg-gray-400 cursor-not-allowed"
                  : "bg-red-600 text-white hover:bg-red-700"
              )}
            >
              {deleteRepository.isPending ? "删除中..." : "确认删除"}
            </button>
            <button
              onClick={() => setShowConfirm(false)}
              className="px-4 py-2 border border-[var(--border)] rounded-lg font-medium text-sm text-[var(--text-primary)] hover:bg-[var(--bg-hover)]"
            >
              取消
            </button>
          </>
        ) : (
          <button
            onClick={() => setShowConfirm(true)}
            className="px-4 py-2 border border-red-300 rounded-lg font-medium text-sm text-red-600 hover:bg-red-50"
          >
            删除
          </button>
        )}
      </div>
    </div>
  );
}
