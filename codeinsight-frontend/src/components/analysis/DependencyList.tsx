"use client";

import { useMemo, useState } from "react";
import { useDependencies } from "@/hooks/use-analysis-results";
import type { ExternalDependency } from "@/api/dependencies";
import { cn } from "@/utils";

interface DependencyListProps {
  repositoryId: string;
}

/** 生态系统展示配置：图标 + 显示名 */
const ECOSYSTEM_CONFIG: Record<string, { icon: string; label: string }> = {
  maven: { icon: "☕", label: "Maven" },
  npm: { icon: "📦", label: "npm" },
  pip: { icon: "🐍", label: "pip" },
  go: { icon: "🐹", label: "Go" },
  cargo: { icon: "🦀", label: "Cargo" },
};

/** 生态系统分组展示顺序 */
const ECOSYSTEM_ORDER = ["maven", "npm", "pip", "go", "cargo"] as const;

/** 作用域配色映射 */
const SCOPE_STYLES: Record<string, string> = {
  compile: "bg-status-info/15 text-status-info",
  dev: "bg-status-warning/15 text-status-warning",
  test: "bg-status-success/15 text-status-success",
  peer: "bg-purple-500/15 text-purple-500",
};

/** 默认作用域标签样式 */
const DEFAULT_SCOPE_STYLE = "bg-gray-500/15 text-gray-500";

/** 作用域过滤选项 */
const SCOPE_OPTIONS = ["", "compile", "dev", "test", "peer"] as const;

/** 生态系统过滤选项占位值 */
const ALL_ECOSYSTEMS = "";

/** 骨架屏占位行数 */
const SKELETON_ROWS = 6;

/** 未知/缺省占位文本 */
const VERSION_FALLBACK = "未指定版本";
const UNKNOWN_LABEL = "未知";

/**
 * 获取生态系统展示配置。
 * @param ecosystem 生态系统名称
 * @returns 图标与显示名
 */
function getEcosystemConfig(ecosystem: string): { icon: string; label: string } {
  return (
    ECOSYSTEM_CONFIG[ecosystem.toLowerCase()] || {
      icon: "📚",
      label: ecosystem || UNKNOWN_LABEL,
    }
  );
}

/**
 * 获取作用域对应的样式类名。
 * @param scope 作用域名
 * @returns Tailwind 类名字符串
 */
function getScopeStyle(scope: string): string {
  return SCOPE_STYLES[scope.toLowerCase()] || DEFAULT_SCOPE_STYLE;
}

/**
 * 按生态系统对依赖项分组，保证顺序稳定。
 * 未在 ECOSYSTEM_ORDER 中的生态系统追加到末尾并按字母序排序。
 * @param deps 依赖列表
 * @returns 有序的 [ecosystem, deps] 数组
 */
function groupByEcosystem(deps: ExternalDependency[]): Array<[string, ExternalDependency[]]> {
  const groups = new Map<string, ExternalDependency[]>();
  for (const dep of deps) {
    const key = dep.ecosystem || UNKNOWN_LABEL;
    const arr = groups.get(key);
    if (arr) arr.push(dep);
    else groups.set(key, [dep]);
  }

  const result: Array<[string, ExternalDependency[]]> = [];
  // 已知顺序
  for (const eco of ECOSYSTEM_ORDER) {
    if (groups.has(eco)) {
      result.push([eco, groups.get(eco)!]);
      groups.delete(eco);
    }
  }
  // 剩余未知生态系统，按字母序追加
  const rest = Array.from(groups.keys()).sort();
  for (const key of rest) {
    result.push([key, groups.get(key)!]);
  }
  return result;
}

/** 作用域标签 */
function ScopeTag({ scope }: { scope: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-sm px-2 py-0.5 text-[10px] font-medium flex-shrink-0",
        getScopeStyle(scope)
      )}
    >
      {scope || UNKNOWN_LABEL}
    </span>
  );
}

/** 过滤工具栏 */
function FilterBar({
  ecosystem,
  setEcosystem,
  scope,
  setScope,
}: {
  ecosystem: string;
  setEcosystem: (v: string) => void;
  scope: string;
  setScope: (v: string) => void;
}) {
  const selectClass =
    "h-8 rounded-md border border-[var(--border)] bg-[var(--bg-card)] px-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand";

  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <select
        value={ecosystem}
        onChange={(e) => setEcosystem(e.target.value)}
        className={selectClass}
        aria-label="生态系统过滤"
      >
        <option value={ALL_ECOSYSTEMS}>全部生态系统</option>
        {ECOSYSTEM_ORDER.map((eco) => {
          const cfg = getEcosystemConfig(eco);
          return (
            <option key={eco} value={eco}>
              {cfg.icon} {cfg.label}
            </option>
          );
        })}
      </select>

      <select
        value={scope}
        onChange={(e) => setScope(e.target.value)}
        className={selectClass}
        aria-label="作用域过滤"
      >
        {SCOPE_OPTIONS.map((s) => (
          <option key={s} value={s}>
            {s === "" ? "全部作用域" : s}
          </option>
        ))}
      </select>
    </div>
  );
}

/** 加载骨架屏 */
function DependencySkeleton() {
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

/** 单个依赖项 */
function DependencyItem({ dep }: { dep: ExternalDependency }) {
  const ecoCfg = getEcosystemConfig(dep.ecosystem);
  const version = dep.version || dep.versionRange || VERSION_FALLBACK;
  const isMaven = dep.ecosystem?.toLowerCase() === "maven";
  const [showFiles, setShowFiles] = useState(false);
  const hasUsedByFiles = dep.usedByFiles && dep.usedByFiles.length > 0;

  return (
    <li>
      <div
        className="flex items-center gap-3 py-1.5 px-3 rounded-md hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
        onClick={() => hasUsedByFiles && setShowFiles(!showFiles)}
      >
        <span className="text-base w-6 flex-shrink-0" title={ecoCfg.label}>
          {ecoCfg.icon}
        </span>

        <div className="flex flex-col min-w-0 flex-1">
          <span className="font-mono text-sm text-[var(--text-primary)] truncate">
            {isMaven && dep.groupName ? (
              <>
                <span className="text-[var(--text-muted)]">{dep.groupName}:</span>
                {dep.artifactName}
              </>
            ) : (
              dep.artifactName
            )}
          </span>
          <span className="font-mono text-xs text-[var(--text-muted)] truncate">
            {version}
            {dep.versionRange && dep.version ? ` (${dep.versionRange})` : ""}
          </span>
        </div>

        <ScopeTag scope={dep.scope} />
        {hasUsedByFiles && (
          <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0">
            {showFiles ? "▲" : "▼"}
          </span>
        )}
      </div>

      {/* 展开引用了该依赖的文件列表 */}
      {showFiles && hasUsedByFiles && (
        <div className="px-5 py-1.5 space-y-0.5 text-xs border-l-2 border-[var(--border)]/60 ml-5 mb-0.5">
          <div className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wider mb-1">
            引用文件 ({dep.usedByFiles.length})
          </div>
          {dep.usedByFiles.map((filePath, idx) => (
            <div key={idx} className="font-mono text-[var(--text-muted)] truncate">
              {filePath}
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

/** 生态系统分组区块 */
function EcosystemGroup({
  ecosystem,
  deps,
}: {
  ecosystem: string;
  deps: ExternalDependency[];
}) {
  const cfg = getEcosystemConfig(ecosystem);
  return (
    <div className="mb-4 last:mb-0">
      <div className="flex items-center gap-2 mb-2.5 pb-2 border-b border-[var(--border)]/60">
        <span className="w-6 h-6 flex items-center justify-center rounded-md bg-[var(--bg-hover)]">{cfg.icon}</span>
        <span className="text-sm font-semibold text-[var(--text-primary)]">
          {cfg.label}
        </span>
        <span className="text-[10px] text-[var(--text-muted)] font-mono bg-[var(--bg-hover)] px-1.5 py-0.5 rounded-sm">({deps.length})</span>
      </div>
      <ul className="space-y-0.5">
        {deps.map((dep) => (
          <DependencyItem key={dep.id} dep={dep} />
        ))}
      </ul>
    </div>
  );
}

/**
 * 外部依赖列表组件。
 * 按生态系统分组展示仓库依赖，支持按生态系统与作用域过滤。
 * @param repositoryId 仓库 ID
 */
export function DependencyList({ repositoryId }: DependencyListProps) {
  const [ecosystem, setEcosystem] = useState("");
  const [scope, setScope] = useState("");

  const params = useMemo(
    () => ({
      ecosystem: ecosystem || undefined,
      scope: scope || undefined,
    }),
    [ecosystem, scope]
  );

  const { data: deps, isLoading, error } = useDependencies(repositoryId, params);

  const grouped = useMemo(
    () => (deps ? groupByEcosystem(deps) : []),
    [deps]
  );

  if (isLoading) {
    return (
      <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">
          外部依赖
        </h3>
        <DependencySkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">
          外部依赖
        </h3>
        <div className="text-red-500 text-sm">加载依赖数据失败</div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
      <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">
        外部依赖
      </h3>

      <FilterBar
        ecosystem={ecosystem}
        setEcosystem={setEcosystem}
        scope={scope}
        setScope={setScope}
      />

      {!deps || deps.length === 0 ? (
        <div className="text-[var(--text-muted)] text-sm py-10 text-center">
          暂无外部依赖数据
        </div>
      ) : (
        grouped.map(([eco, items]) => (
          <EcosystemGroup
            key={eco}
            ecosystem={eco}
            deps={items}
          />
        ))
      )}
    </div>
  );
}
