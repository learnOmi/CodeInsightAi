"use client";

import { useSSE } from "@/hooks/use-sse";

interface AnalysisProgressProps {
  taskId: string;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export function AnalysisProgress({ taskId, onComplete, onError }: AnalysisProgressProps) {
  const { data, error, isComplete } = useSSE(taskId, true);

  // 通知外部完成/错误状态
  if (isComplete && data && onComplete) {
    // 延迟执行，避免在渲染中触发状态更新
    setTimeout(() => onComplete(), 0);
  }
  if (error && onError) {
    setTimeout(() => onError(error), 0);
  }

  if (error) {
    return (
      <div className="bg-status-error/10 border border-status-error/30 rounded-lg p-4">
        <div className="flex items-center gap-2">
          <span className="text-status-error text-lg">&#x2716;</span>
          <div>
            <p className="text-sm font-medium text-status-error">分析失败</p>
            <p className="text-xs text-[var(--text-secondary)] mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-brand border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-[var(--text-secondary)]">正在连接分析服务...</p>
        </div>
      </div>
    );
  }

  if (isComplete) {
    return (
      <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
        <div className="flex items-center gap-2">
          <span className="text-green-500 text-lg">&#x2714;</span>
          <div>
            <p className="text-sm font-medium text-green-600">分析完成</p>
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              已发现 {data.progress.knowledgePointsFound} 个知识点
            </p>
          </div>
        </div>
      </div>
    );
  }

  const percent = Math.round(data.progress.percent);

  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border)] rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 border-2 border-brand border-t-transparent rounded-full animate-spin" />
          <p className="text-sm font-medium text-[var(--text-primary)]">分析进行中</p>
        </div>
        <span className="text-sm text-[var(--text-secondary)]">{percent}%</span>
      </div>
      <div className="w-full bg-[var(--bg-hover)] rounded-full h-2">
        <div
          className="bg-brand h-2 rounded-full transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="flex justify-between mt-2 text-xs text-[var(--text-muted)]">
        <span>步骤: {data.progress.currentStep}</span>
        <span>
          文件: {data.progress.filesProcessed}/{data.progress.filesTotal}
        </span>
        <span>知识点: {data.progress.knowledgePointsFound}</span>
      </div>
    </div>
  );
}