"use client";

import { useMemo } from "react";
import type { RouteMiddleware } from "@/api/routes";

/** 中间件类型配色方案 */
const MIDDLEWARE_TYPE_STYLES: Record<string, {
  bg: string;
  border: string;
  text: string;
  badgeBg: string;
  badgeText: string;
}> = {
  authentication: {
    bg: "rgba(239, 68, 68, 0.08)",
    border: "#ef4444",
    text: "#b91c1c",
    badgeBg: "rgba(239, 68, 68, 0.15)",
    badgeText: "#dc2626",
  },
  rate_limiting: {
    bg: "rgba(249, 115, 22, 0.08)",
    border: "#f97316",
    text: "#c2410c",
    badgeBg: "rgba(249, 115, 22, 0.15)",
    badgeText: "#ea580c",
  },
  logging: {
    bg: "rgba(59, 130, 246, 0.08)",
    border: "#3b82f6",
    text: "#1d4ed8",
    badgeBg: "rgba(59, 130, 246, 0.15)",
    badgeText: "#2563eb",
  },
  cors: {
    bg: "rgba(34, 197, 94, 0.08)",
    border: "#22c55e",
    text: "#15803d",
    badgeBg: "rgba(34, 197, 94, 0.15)",
    badgeText: "#16a34a",
  },
  default: {
    bg: "rgba(107, 114, 128, 0.08)",
    border: "#6b7280",
    text: "#4b5563",
    badgeBg: "rgba(107, 114, 128, 0.15)",
    badgeText: "#6b7280",
  },
};

/** 获取中间件类型的配色（未知类型回退到 default） */
function getMiddlewareStyle(type: string) {
  return MIDDLEWARE_TYPE_STYLES[type] || MIDDLEWARE_TYPE_STYLES.default;
}

/** 缩短文件路径，便于在卡片中展示 */
function shortFilePath(filePath: string, maxLen = 28): string {
  if (!filePath || filePath.length <= maxLen) return filePath || "";
  const parts = filePath.split(/[/\\]/);
  let result = parts[parts.length - 1];
  for (let i = parts.length - 2; i >= 0; i--) {
    const candidate = `${parts[i]}/${result}`;
    if (candidate.length > maxLen) break;
    result = candidate;
  }
  return `…/${result}`;
}

interface MiddlewareChainProps {
  /** 路由的中间件列表，将按 order 字段排序后展示 */
  middlewares: RouteMiddleware[];
}

/**
 * 中间件链可视化组件
 *
 * 以水平排列的 DAG（有向无环图）样式展示路由的中间件执行顺序：
 * - 每个中间件显示为卡片节点（包含名称、类型、文件路径）
 * - 节点之间用箭头连接，表示执行顺序
 * - 按 order 字段升序排序
 * - 不同中间件类型采用不同的配色方案
 */
export function MiddlewareChain({ middlewares }: MiddlewareChainProps) {
  // 按 order 字段排序，确保稳定展示执行顺序
  const sortedMiddlewares = useMemo(() => {
    if (!middlewares || middlewares.length === 0) return [];
    return [...middlewares].sort((a, b) => a.order - b.order);
  }, [middlewares]);

  if (!middlewares || middlewares.length === 0) {
    return (
      <div className="flex items-center justify-center py-6 text-sm text-[var(--text-muted)]">
        无中间件
      </div>
    );
  }

  return (
    <div className="overflow-x-auto py-2">
      <div className="flex items-stretch gap-0 min-w-max">
        {sortedMiddlewares.map((mw, index) => {
          const style = getMiddlewareStyle(mw.type);
          const isLast = index === sortedMiddlewares.length - 1;
          return (
            <div key={`${mw.name}-${mw.order}-${index}`} className="flex items-stretch">
              {/* 中间件卡片节点 */}
              <div
                className="flex flex-col justify-between rounded-lg border-2 px-3 py-2 min-w-[180px] max-w-[220px]"
                style={{
                  backgroundColor: style.bg,
                  borderColor: style.border,
                }}
              >
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span
                    className="inline-flex items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-semibold flex-shrink-0"
                    style={{
                      backgroundColor: style.badgeBg,
                      color: style.badgeText,
                    }}
                  >
                    {mw.type}
                  </span>
                  <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0">
                    #{mw.order}
                  </span>
                </div>
                <div
                  className="text-sm font-semibold truncate leading-tight"
                  style={{ color: style.text }}
                  title={mw.name}
                >
                  {mw.name}
                </div>
                <div
                  className="text-[11px] font-mono truncate mt-1"
                  style={{ color: "var(--text-muted)" }}
                  title={mw.file}
                >
                  {shortFilePath(mw.file)}
                </div>
              </div>
              {/* 箭头连接：表示执行顺序 */}
              {!isLast && (
                <div className="flex items-center justify-center px-2 flex-shrink-0">
                  <svg
                    width="24"
                    height="16"
                    viewBox="0 0 24 16"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                  >
                    <path
                      d="M2 8 L20 8"
                      stroke="var(--text-muted)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                    <path
                      d="M14 3 L21 8 L14 13"
                      stroke="var(--text-muted)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                    />
                  </svg>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
