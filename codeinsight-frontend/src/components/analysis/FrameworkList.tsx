"use client";

import { useMemo, useState } from "react";
import { useFrameworks } from "@/hooks/use-analysis-results";

/** 框架分类显示名称 */
const FRAMEWORK_CATEGORY_LABELS: Record<string, string> = {
  frontend: "前端",
  backend: "后端",
  database: "数据库",
  messaging: "消息队列",
  testing: "测试",
  build: "构建工具",
  other: "其他",
};

/** 分类配色 */
const FRAMEWORK_CATEGORY_COLORS: Record<string, string> = {
  frontend: "bg-blue-100 text-blue-700",
  backend: "bg-purple-100 text-purple-700",
  database: "bg-green-100 text-green-700",
  messaging: "bg-orange-100 text-orange-700",
  testing: "bg-yellow-100 text-yellow-700",
  build: "bg-cyan-100 text-cyan-700",
  other: "bg-gray-100 text-gray-700",
};

/** 框架名称显示映射 */
const FRAMEWORK_DISPLAY_NAMES: Record<string, string> = {
  spring_boot: "Spring Boot",
  react: "React",
  vue: "Vue",
  angular: "Angular",
  express: "Express",
  koa: "Koa",
  flask: "Flask",
  fastapi: "FastAPI",
  django: "Django",
  gin: "Gin",
  echo: "Echo",
  typeorm: "TypeORM",
  mybatis: "MyBatis",
  jpa: "JPA",
  redis: "Redis",
  kafka: "Kafka",
  rabbitmq: "RabbitMQ",
  jest: "Jest",
  pytest: "pytest",
  webpack: "Webpack",
  vite: "Vite",
};

/** 置信度等级 */
function getConfidenceLevel(confidence: number): { label: string; color: string } {
  if (confidence >= 0.8) return { label: "高", color: "text-green-600" };
  if (confidence >= 0.5) return { label: "中", color: "text-yellow-600" };
  return { label: "低", color: "text-gray-500" };
}

interface FrameworkListProps {
  repositoryId: string;
}

/** 框架检测结果列表 */
export function FrameworkList({ repositoryId }: FrameworkListProps) {
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [minConfidence, setMinConfidence] = useState<number>(0);

  const params = useMemo(
    () => ({
      category: categoryFilter || undefined,
      minConfidence: minConfidence > 0 ? minConfidence : undefined,
    }),
    [categoryFilter, minConfidence]
  );

  const { data: frameworks, isLoading, error } = useFrameworks(repositoryId, params);

  const categories = useMemo(() => {
    if (!frameworks) return [];
    const set = new Set(frameworks.map((f) => f.category));
    return Array.from(set).sort();
  }, [frameworks]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="h-8 bg-[var(--bg-hover)] rounded animate-pulse" />
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="h-20 bg-[var(--bg-hover)] rounded animate-pulse"
            style={{ width: `${90 - i * 5}%` }}
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-status-error text-sm py-4">{"加载框架检测数据失败"}</div>
    );
  }

  if (!frameworks || frameworks.length === 0) {
    return (
      <div className="text-center text-[var(--text-muted)] text-sm py-10">
        {"暂无框架检测数据"}
      </div>
    );
  }

  return (
    <div>
      {/* 过滤栏 */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">{"分类"}</label>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="text-sm bg-[var(--bg-card)] border border-[var(--border)] rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand text-[var(--text-primary)]"
          >
            <option value="">{"全部"}</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {FRAMEWORK_CATEGORY_LABELS[cat] ?? cat}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">{"最低置信度"}</label>
          <select
            value={minConfidence}
            onChange={(e) => setMinConfidence(Number(e.target.value))}
            className="text-sm bg-[var(--bg-card)] border border-[var(--border)] rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand text-[var(--text-primary)]"
          >
            <option value={0}>{"全部"}</option>
            <option value={0.3}>{"0.3+"}</option>
            <option value={0.5}>{"0.5+"}</option>
            <option value={0.8}>{"0.8+"}</option>
          </select>
        </div>
        <span className="text-[10px] text-[var(--text-muted)] font-mono bg-[var(--bg-hover)] px-2 py-0.5 rounded-sm ml-auto">
          {frameworks.length} {"个框架"}
        </span>
      </div>

      {/* 框架卡片网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {frameworks.map((fw) => {
          const confidence = getConfidenceLevel(fw.confidence);
          const categoryColor =
            FRAMEWORK_CATEGORY_COLORS[fw.category] ??
            FRAMEWORK_CATEGORY_COLORS.other;
          const displayName =
            FRAMEWORK_DISPLAY_NAMES[fw.framework] ?? fw.framework;

          return (
            <div
              key={fw.id}
              className="group relative rounded-xl overflow-hidden bg-[var(--bg-card)] transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[var(--glow-brand-light)]"
            >
              {/* 渐变边框层 — hover 时显现 */}
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-brand/20 via-brand/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              {/* 顶部光条 */}
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

              <div className="relative m-[1px] rounded-xl bg-[var(--bg-card)] p-3.5">
                {/* 框架名称 + 分类 */}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-[var(--text-primary)] group-hover:text-brand transition-colors">
                    {displayName}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${categoryColor}`}
                  >
                    {FRAMEWORK_CATEGORY_LABELS[fw.category] ?? fw.category}
                  </span>
                </div>

                {/* 置信度 — 更细 */}
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex-1 h-1 bg-[var(--bg-hover)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-brand to-brand-fg rounded-full transition-all"
                      style={{ width: `${fw.confidence * 100}%` }}
                    />
                  </div>
                  <span className={`text-[10px] font-mono tabular-nums ${confidence.color}`}>
                    {(fw.confidence * 100).toFixed(0)}%
                  </span>
                </div>

                {/* 证据信息 */}
                {Object.keys(fw.evidence).length > 0 && (
                  <div className="text-[10px] text-[var(--text-muted)] space-y-0.5 font-mono">
                    {Object.entries(fw.evidence).map(([key, value]) => (
                      <div key={key} className="truncate">
                        <span className="font-mono">{key}:</span>{" "}
                        <span className="font-mono">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}