"use client";

import { useRepositoryStats } from "@/hooks/use-analysis-results";

interface RepositoryOverviewProps {
  repositoryId: string;
}

const METER_COLORS = [
  "bg-blue-500",
  "bg-green-500",
  "bg-purple-500",
  "bg-amber-500",
  "bg-rose-500",
  "bg-cyan-500",
  "bg-orange-500",
];

/**
 * 仓库概览仪表盘组件
 *
 * 一站式展示项目的全局统计信息，帮助用户快速把握项目规模与技术栈组成。
 */
export function RepositoryOverview({ repositoryId }: RepositoryOverviewProps) {
  const { data: stats, isLoading, error } = useRepositoryStats(repositoryId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">项目概览</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="h-20 bg-[var(--bg-hover)] rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div>
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">项目概览</h3>
        <div className="text-red-500 text-sm">加载统计信息失败</div>
      </div>
    );
  }

  const langEntries = Object.entries(stats.languageDistribution);
  const langTotal = langEntries.reduce((s, [, c]) => s + c, 0);

  const nodeTypeEntries = Object.entries(stats.nodeTypeDistribution);
  const edgeTypeEntries = Object.entries(stats.edgeTypeDistribution);
  const ecoEntries = Object.entries(stats.ecosystemDistribution);

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">项目概览</h3>

      {/* 顶部分类统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="文件" value={stats.fileCount} sub={`${stats.totalLines} 行代码`} />
        <StatCard label="AST 节点" value={stats.nodeCount} sub={`${nodeTypeEntries.length} 种类型`} />
        <StatCard label="调用关系" value={stats.edgeCount} sub={`${edgeTypeEntries.length} 种调用类型`} />
        <StatCard
          label="模块依赖"
          value={stats.moduleDependencyCount}
          sub={`${Math.round(stats.moduleDependencyCount / Math.max(stats.fileCount, 1) * 10) / 10} 依赖/文件`}
        />
        <StatCard label="外部依赖" value={stats.externalDependencyCount} sub={`${ecoEntries.length} 个生态系统`} />
        <StatCard label="框架" value={stats.frameworkCount} sub="检测到的技术框架" />
        <StatCard label="API 路由" value={stats.routeCount} sub="HTTP 端点" />
      </div>

      {/* 语言分布 + 节点类型分布 + 调用类型分布 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 语言分布 */}
        <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">语言分布</h4>
          {langEntries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">暂无数据</p>
          ) : (
            <div className="space-y-2">
              {langEntries.map(([lang, count], idx) => (
                <BarRow
                  key={lang}
                  label={lang}
                  count={count}
                  total={langTotal}
                  barColor={METER_COLORS[idx % METER_COLORS.length]}
                />
              ))}
            </div>
          )}
        </div>

        {/* AST 节点类型分布 */}
        <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">节点类型分布</h4>
          {nodeTypeEntries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">暂无数据</p>
          ) : (
            <div className="space-y-1.5">
              {nodeTypeEntries.slice(0, 8).map(([type, count]) => {
                const pct = Math.round((count / stats.nodeCount) * 100);
                return (
                  <div key={type} className="flex items-center gap-2 text-xs">
                    <span className="w-20 text-[var(--text-muted)] truncate flex-shrink-0">{type}</span>
                    <div className="flex-1 h-2 bg-[var(--bg-hover)] rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-12 text-right text-[var(--text-muted)] font-mono tabular-nums">{pct}%</span>
                  </div>
                );
              })}
              {nodeTypeEntries.length > 8 && (
                <p className="text-xs text-[var(--text-muted)] text-center pt-1">
                  还有 {nodeTypeEntries.length - 8} 种类型...
                </p>
              )}
            </div>
          )}
        </div>

        {/* 调用类型分布 */}
        <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">调用类型分布</h4>
          {edgeTypeEntries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">暂无数据</p>
          ) : (
            <div className="space-y-1.5">
              {edgeTypeEntries.map(([type, count]) => {
                const pct = Math.round((count / stats.edgeCount) * 100);
                return (
                  <div key={type} className="flex items-center gap-2 text-xs">
                    <span className="w-20 text-[var(--text-muted)] truncate flex-shrink-0">{type}</span>
                    <div className="flex-1 h-2 bg-[var(--bg-hover)] rounded-full overflow-hidden">
                      <div className="h-full bg-purple-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-16 text-right text-[var(--text-muted)] font-mono tabular-nums flex-shrink-0">
                      {count} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* 生态系统分布 */}
      {ecoEntries.length > 0 && (
        <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">外部依赖生态系统</h4>
          <div className="flex flex-wrap gap-2">
            {ecoEntries.map(([eco, count]) => (
              <span
                key={eco}
                className="inline-flex items-center gap-1 rounded-full bg-[var(--bg-hover)] px-2.5 py-1 text-xs text-[var(--text-primary)]"
              >
                {eco}
                <span className="font-mono text-[var(--text-muted)]">({count})</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 统计卡片 */
function StatCard({ label, value, sub }: { label: string; value: number; sub: string }) {
  return (
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] p-3.5 hover:shadow-sm transition-shadow">
      <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-1">{label}</div>
      <div className="text-xl font-bold text-[var(--text-primary)] font-mono tabular-nums">{value.toLocaleString()}</div>
      <div className="text-[10px] text-[var(--text-muted)] mt-0.5 truncate">{sub}</div>
    </div>
  );
}

/** 横向条形图行 */
function BarRow({
  label,
  count,
  total,
  barColor,
}: {
  label: string;
  count: number;
  total: number;
  barColor: string;
}) {
  const pct = Math.round((count / total) * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-16 text-[var(--text-muted)] truncate flex-shrink-0">{label}</span>
      <div className="flex-1 h-3 bg-[var(--bg-hover)] rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-16 text-right text-[var(--text-muted)] font-mono tabular-nums flex-shrink-0">
        {count} ({pct}%)
      </span>
    </div>
  );
}
