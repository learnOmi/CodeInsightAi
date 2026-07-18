"use client";

import { useMemo, useState } from "react";
import { useRoutes } from "@/hooks/use-analysis-results";
import { useFiles } from "@/hooks/use-files";
import type { ApiRoute } from "@/api/routes";
import { MiddlewareChain } from "./MiddlewareChain";
import { cn } from "@/utils";
import type { NavigableProps } from "./NavTrailBar";

interface RouteListProps extends NavigableProps {
  repositoryId: string;
}

/** HTTP 方法配色映射 */
const HTTP_METHOD_STYLES: Record<string, string> = {
  GET: "bg-status-success/15 text-status-success",
  POST: "bg-status-info/15 text-status-info",
  PUT: "bg-status-warning/15 text-status-warning",
  DELETE: "bg-status-error/15 text-status-error",
  PATCH: "bg-purple-500/15 text-purple-500",
};

/** HTTP 方法过滤选项 */
const HTTP_METHOD_OPTIONS = ["", "GET", "POST", "PUT", "DELETE", "PATCH"] as const;

/** 框架过滤的「全部」选项占位值 */
const ALL_FRAMEWORKS = "";

/** 骨架屏占位行数 */
const SKELETON_ROWS = 6;

/** 默认 HTTP 方法标签样式（未匹配时使用） */
const DEFAULT_METHOD_STYLE = "bg-gray-100 text-gray-700";

/**
 * 获取 HTTP 方法对应的样式类名。
 * @param method HTTP 方法名（GET/POST/PUT/DELETE/PATCH 等）
 * @returns Tailwind 类名字符串
 */
function getMethodStyle(method: string): string {
  return HTTP_METHOD_STYLES[method.toUpperCase()] || DEFAULT_METHOD_STYLE;
}

/**
 * 从路由列表中收集所有出现过的框架名称，用于框架过滤下拉。
 * @param routes 路由数据
 * @returns 去重排序后的框架名称数组
 */
function collectFrameworks(routes: ApiRoute[]): string[] {
  const set = new Set<string>();
  for (const r of routes) {
    if (r.framework) set.add(r.framework);
  }
  return Array.from(set).sort();
}

/** HTTP 方法标签 */
function MethodTag({ method }: { method: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-sm px-2 py-0.5 text-[10px] font-bold min-w-[52px] tracking-wide flex-shrink-0",
        getMethodStyle(method)
      )}
    >
      {method.toUpperCase()}
    </span>
  );
}

/** 中间件数量徽章 */
function MiddlewareBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span
      className="inline-flex items-center rounded-sm bg-[var(--bg-hover)] px-2 py-0.5 text-[10px] text-[var(--text-muted)] flex-shrink-0"
      title={`${count} 个中间件`}
    >
      MW: {count}
    </span>
  );
}

/** 过滤工具栏 */
function FilterBar({
  httpMethod,
  setHttpMethod,
  framework,
  setFramework,
  pathPattern,
  setPathPattern,
  frameworkOptions,
}: {
  httpMethod: string;
  setHttpMethod: (v: string) => void;
  framework: string;
  setFramework: (v: string) => void;
  pathPattern: string;
  setPathPattern: (v: string) => void;
  frameworkOptions: string[];
}) {
  const selectClass =
    "h-8 rounded-md border border-[var(--border)] bg-[var(--bg-card)] px-2.5 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand";

  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <select
        value={httpMethod}
        onChange={(e) => setHttpMethod(e.target.value)}
        className={selectClass}
        aria-label="HTTP 方法过滤"
      >
        {HTTP_METHOD_OPTIONS.map((m) => (
          <option key={m} value={m}>
            {m === "" ? "全部方法" : m}
          </option>
        ))}
      </select>

      <select
        value={framework}
        onChange={(e) => setFramework(e.target.value)}
        className={selectClass}
        aria-label="框架过滤"
      >
        <option value={ALL_FRAMEWORKS}>全部框架</option>
        {frameworkOptions.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </select>

      <input
        type="text"
        value={pathPattern}
        onChange={(e) => setPathPattern(e.target.value)}
        placeholder="搜索路径..."
        className="h-8 flex-1 min-w-[160px] rounded-md border border-[var(--border)] bg-[var(--bg-card)] px-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand"
      />
    </div>
  );
}

/** 加载骨架屏 */
function RouteSkeleton() {
  return (
    <div className="space-y-2">
      {[...Array(SKELETON_ROWS)].map((_, i) => (
        <div
          key={i}
          className="h-8 bg-[var(--bg-hover)] rounded animate-pulse"
          style={{ width: `${85 - i * 4}%` }}
        />
      ))}
    </div>
  );
}

/** 单行路由（可点击展开中间件链） */
function RouteRow({ route, onNavigate, filePathToIdMap }: { route: ApiRoute; onNavigate?: NavigableProps["onNavigate"]; filePathToIdMap: Map<string, string> }) {
  const [expanded, setExpanded] = useState(false);
  const hasMiddlewares = (route.middlewares?.length ?? 0) > 0;
  const fileId = route.handlerFile ? filePathToIdMap.get(route.handlerFile) : undefined;

  return (
    <li>
      <div
        className="flex items-center gap-3 py-1.5 px-3 rounded-md hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
        onClick={() => hasMiddlewares && setExpanded(!expanded)}
      >
        <MethodTag method={route.httpMethod} />
        <span className="font-mono text-sm text-[var(--text-primary)] truncate flex-1 min-w-0">
          {route.pathPattern}
        </span>
        <span className="text-xs text-[var(--text-secondary)] truncate max-w-[30%] hidden sm:inline">
          {route.handlerFunction}
        </span>
        <span className="text-xs text-[var(--text-muted)] flex-shrink-0 hidden md:inline">
          {route.framework}
        </span>
        <MiddlewareBadge count={route.middlewares?.length ?? 0} />
        {fileId && onNavigate && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onNavigate({ component: "callgraph", fileId: fileId, label: route.handlerFile, detail: "调用图" });
            }}
            className="text-[10px] px-1.5 py-0.5 rounded bg-brand/10 text-brand hover:bg-brand/20 transition-colors flex-shrink-0"
            title="查看调用图"
          >
            ⊙调用图
          </button>
        )}
        {hasMiddlewares && (
          <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0">
            {expanded ? "▲" : "▼"}
          </span>
        )}
      </div>

      {/* 展开的中间件链 */}
      {expanded && route.middlewares && route.middlewares.length > 0 && (
        <div className="px-4 py-2.5 border-l-2 border-[var(--border)]/60 ml-4 mb-1">
          <div className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wider mb-2">中间件链</div>
          <MiddlewareChain middlewares={route.middlewares} />
        </div>
      )}
    </li>
  );
}

/**
 * API 路由列表组件。
 * 展示仓库下解析出的 API 路由，支持按 HTTP 方法、框架、路径模式过滤。
 * @param repositoryId 仓库 ID
 */
export function RouteList({ repositoryId, onNavigate }: RouteListProps) {
  const [httpMethod, setHttpMethod] = useState("");
  const [framework, setFramework] = useState("");
  const [pathPattern, setPathPattern] = useState("");

  const params = useMemo(
    () => ({
      httpMethod: httpMethod || undefined,
      framework: framework || undefined,
      pathPattern: pathPattern || undefined,
    }),
    [httpMethod, framework, pathPattern]
  );

  const { data: routes, isLoading, error } = useRoutes(repositoryId, params);

  // 独立获取一次无过滤路由数据，用于构建稳定的框架下拉选项。
  // React Query 按 queryKey 区分缓存（params 为 undefined），不会与上方过滤请求混用。
  const { data: allRoutesForFrameworks } = useRoutes(repositoryId);
  const frameworkOptions = useMemo(
    () => (allRoutesForFrameworks ? collectFrameworks(allRoutesForFrameworks) : []),
    [allRoutesForFrameworks]
  );

  const { data: files } = useFiles(repositoryId);

  const filePathToIdMap = useMemo(() => {
    const map = new Map<string, string>();
    files?.forEach((f) => map.set(f.path, f.id));
    return map;
  }, [files]);

  if (isLoading) {
    return (
      <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">
          API 路由
        </h3>
        <RouteSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">
          API 路由
        </h3>
        <div className="text-status-error text-sm">加载路由数据失败</div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
      <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">
        API 路由
      </h3>

      <FilterBar
        httpMethod={httpMethod}
        setHttpMethod={setHttpMethod}
        framework={framework}
        setFramework={setFramework}
        pathPattern={pathPattern}
        setPathPattern={setPathPattern}
        frameworkOptions={frameworkOptions}
      />

      {!routes || routes.length === 0 ? (
        <div className="text-[var(--text-muted)] text-sm py-10 text-center">
          暂无 API 路由数据
        </div>
      ) : (
        <ul className="space-y-0.5">
          {routes.map((route) => (
            <RouteRow key={route.id} route={route} onNavigate={onNavigate} filePathToIdMap={filePathToIdMap} />
          ))}
        </ul>
      )}
    </div>
  );
}
