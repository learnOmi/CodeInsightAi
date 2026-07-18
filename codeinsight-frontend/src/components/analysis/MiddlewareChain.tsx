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
    bg: "hsl(0 84% 60% / 0.08)",
    border: "var(--color-mw-auth)",
    text: "hsl(0 60% 40%)",
    badgeBg: "hsl(0 84% 60% / 0.15)",
    badgeText: "var(--color-mw-auth)",
  },
  rate_limiting: {
    bg: "hsl(24 94% 50% / 0.08)",
    border: "var(--color-mw-rate-limit)",
    text: "hsl(24 70% 40%)",
    badgeBg: "hsl(24 94% 50% / 0.15)",
    badgeText: "var(--color-mw-rate-limit)",
  },
  logging: {
    bg: "hsl(217 91% 60% / 0.08)",
    border: "var(--color-mw-logging)",
    text: "hsl(217 70% 40%)",
    badgeBg: "hsl(217 91% 60% / 0.15)",
    badgeText: "var(--color-mw-logging)",
  },
  cors: {
    bg: "hsl(152 71% 48% / 0.08)",
    border: "var(--color-mw-cors)",
    text: "hsl(152 60% 35%)",
    badgeBg: "hsl(152 71% 48% / 0.15)",
    badgeText: "var(--color-mw-cors)",
  },
  default: {
    bg: "hsl(215 10% 47% / 0.08)",
    border: "var(--text-muted)",
    text: "var(--text-secondary)",
    badgeBg: "hsl(215 10% 47% / 0.15)",
    badgeText: "var(--text-muted)",
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
      <div className="flex items-center justify-center text-center py-8 text-sm text-[var(--text-muted)]">
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
                className="flex flex-col justify-between rounded-lg border-2 px-3 py-2.5 min-w-[170px] max-w-[220px] transition-all duration-200 hover:shadow-md hover:-translate-y-0.5"
                style={{
                  backgroundColor: style.bg,
                  borderColor: style.border + "60",
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
                  className="text-[10px] font-mono truncate mt-1"
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
                      style={{ opacity: 0.5 }}
                    />
                    <path
                      d="M14 3 L21 8 L14 13"
                      stroke="var(--text-muted)"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      fill="none"
                      style={{ opacity: 0.5 }}
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
