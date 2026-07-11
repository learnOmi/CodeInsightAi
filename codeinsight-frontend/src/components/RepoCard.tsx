"use client";

import { useState } from "react";
import {
  useSubmitAnalysis,
  useCancelTask,
  useDeleteRepository,
  useTaskStatus,
} from "@/hooks/use-repositories";
import { APIError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];

interface RepoCardProps {
  repository: Repository;
}

const statusConfig: Record<string, { label: string; color: string }> = {
  pending: { label: "待分析", color: "bg-gray-100 text-gray-800" },
  analyzing: { label: "分析中", color: "bg-blue-100 text-blue-800" },
  completed: { label: "已完成", color: "bg-green-100 text-green-800" },
  failed: { label: "失败", color: "bg-red-100 text-red-800" },
  cancelled: { label: "已取消", color: "bg-yellow-100 text-yellow-800" },
};

const taskStatusLabels: Record<string, string> = {
  pending: "等待中",
  scanning: "扫描文件",
  parsing: "解析代码",
  analyzing_modules: "分析模块",
  storing: "存储结果",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export function RepoCard({ repository }: RepoCardProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const submitAnalysis = useSubmitAnalysis();
  const cancelTask = useCancelTask();
  const deleteRepository = useDeleteRepository();

  const isAnalyzing = repository.status === "analyzing";
  const taskId = repository.id;

  const { data: taskData } = useTaskStatus(
    isAnalyzing ? taskId : "",
    isAnalyzing
  ) as { data: components["schemas"]["AnalysisTask"] | undefined };

  const handleSubmitAnalysis = async () => {
    setSubmitError("");
    try {
      await submitAnalysis.mutateAsync({ repositoryId: repository.id });
    } catch (err) {
      if (err instanceof APIError) {
        if (err.status === 409) {
          setSubmitError("已有分析任务正在进行");
        } else {
          setSubmitError(err.message);
        }
      } else {
        setSubmitError("提交失败，请重试");
      }
    }
  };

  const handleCancelTask = async () => {
    if (taskData?.taskId) {
      await cancelTask.mutateAsync(taskData.taskId);
    }
  };

  const handleDelete = async () => {
    await deleteRepository.mutateAsync(repository.id);
    setShowConfirm(false);
  };

  const status = statusConfig[repository.status] || statusConfig.pending;
  const progress = taskData?.progress || { percent: 0, filesProcessed: 0, filesTotal: 0 };
  const currentStep = taskData?.progress?.currentStep ? taskStatusLabels[taskData.progress.currentStep] : "";

  return (
    <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">{repository.name}</h3>
          <p className="text-sm text-gray-500 truncate max-w-xs">{repository.path}</p>
        </div>
        <span
          className={cn(
            "px-3 py-1 rounded-full text-xs font-medium",
            status.color
          )}
        >
          {status.label}
        </span>
      </div>

      {isAnalyzing && (
        <div className="mb-4 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">{currentStep || "分析中"}</span>
            <span className="text-gray-600">{progress.percent}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress.percent}%` }}
            />
          </div>
          <div className="text-xs text-gray-500">
            {progress.filesProcessed} / {progress.filesTotal} 文件
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="text-center">
          <div className="text-xl font-bold text-gray-900">{repository.fileCount}</div>
          <div className="text-xs text-gray-500">文件数</div>
        </div>
        <div className="text-center">
          <div className="text-xl font-bold text-gray-900">{repository.lineCount}</div>
          <div className="text-xs text-gray-500">代码行数</div>
        </div>
        <div className="text-center">
          <div className="text-xl font-bold text-gray-900">{repository.knowledgePointsCount}</div>
          <div className="text-xs text-gray-500">知识点</div>
        </div>
      </div>

      {submitError && (
        <div className="text-red-600 text-sm mb-3">{submitError}</div>
      )}

      <div className="flex gap-2">
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
              className="px-4 py-2 border border-gray-300 rounded-lg font-medium text-sm text-gray-700 hover:bg-gray-50"
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