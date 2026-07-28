"use client";

import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const { data: stats, isLoading, error } = useRepositoryStats(repositoryId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">{t("overview.heading")}</h3>
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
        <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">{t("overview.heading")}</h3>
        <div className="text-red-500 text-sm">{t("overview.loadError")}</div>
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
      <h3 className="text-base font-semibold mb-3 tracking-tight text-[var(--text-primary)]">{t("overview.heading")}</h3>

      {/* 顶部分类统计卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label={t("overview.files")} value={stats.fileCount} sub={`${stats.totalLines} ${t("overview.codeLines")}`} />
        <StatCard label={t("overview.astNodes")} value={stats.nodeCount} sub={t("overview.types", { n: nodeTypeEntries.length })} />
        <StatCard label={t("overview.callRelations")} value={stats.edgeCount} sub={t("overview.callTypes", { n: edgeTypeEntries.length })} />
        <StatCard
          label={t("overview.moduleDeps")}
          value={stats.moduleDependencyCount}
          sub={`${Math.round(stats.moduleDependencyCount / Math.max(stats.fileCount, 1) * 10) / 10} ${t("overview.depsPerFile")}`}
        />
        <StatCard label={t("overview.externalDeps")} value={stats.externalDependencyCount} sub={t("overview.ecosystems", { n: ecoEntries.length })} />
        <StatCard label={t("overview.frameworks")} value={stats.frameworkCount} sub={t("overview.detectedFrameworks")} />
        <StatCard label={t("overview.apiRoutes")} value={stats.routeCount} sub={t("overview.httpEndpoints")} />
      </div>

      {/* 语言分布 + 节点类型分布 + 调用类型分布 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 语言分布 */}
        <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">{t("overview.langDistribution")}</h4>
          {langEntries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">{t("overview.noData")}</p>
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
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">{t("overview.nodeTypeDist")}</h4>
          {nodeTypeEntries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">{t("overview.noData")}</p>
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
                  {t("overview.moreTypes", { n: nodeTypeEntries.length - 8 })}
                </p>
              )}
            </div>
          )}
        </div>

        {/* 调用类型分布 */}
        <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] p-5">
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">{t("overview.callTypeDist")}</h4>
          {edgeTypeEntries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">{t("overview.noData")}</p>
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
          <h4 className="text-xs font-semibold mb-3 text-[var(--text-muted)] uppercase tracking-wider">{t("overview.depEcosystems")}</h4>
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
    <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border)] p-3.5 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[var(--glow-brand-light)] group">
      <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-1 group-hover:text-brand transition-colors">{label}</div>
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
