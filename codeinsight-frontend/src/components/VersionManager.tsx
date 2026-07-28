"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useVersions, useSwitchVersion, useRollbackVersion } from "@/hooks/use-repositories";
import { StatusBadge } from "@/components/analysis-status";
import type { components } from "@codeinsight/shared";

type AnalysisVersion = components["schemas"]["AnalysisVersion"];

interface VersionManagerProps {
  repositoryId: string;
}

export function VersionManager({ repositoryId }: VersionManagerProps) {
  const { t } = useTranslation();
  const { data: versions, isLoading } = useVersions(repositoryId);
  const switchVersion = useSwitchVersion();
  const rollbackVersion = useRollbackVersion();
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);
  const [showRollbackConfirm, setShowRollbackConfirm] = useState(false);
  const [error, setError] = useState("");

  const handleSwitch = async (version: string) => {
    setError("");
    try {
      await switchVersion.mutateAsync({ repositoryId, version });
    } catch (_err) {
      setError(t("versionManager.switchError"));
    }
  };

  const handleRollback = async () => {
    if (!selectedVersion) return;
    setError("");
    try {
      await rollbackVersion.mutateAsync({ repositoryId, version: selectedVersion });
      setShowRollbackConfirm(false);
      setSelectedVersion(null);
    } catch (_err) {
      setError(t("versionManager.rollbackError"));
    }
  };

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString("zh-CN");
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-2 border-brand border-t-transparent"></div>
      </div>
    );
  }

  if (!versions || versions.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--text-muted)]">
        {t("versionManager.empty")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg bg-status-error/10 text-status-error px-3 py-2 text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)]/60">
              <th className="text-left py-2.5 px-4 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{t("versionManager.version")}</th>
              <th className="text-left py-2.5 px-4 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{t("versionManager.status")}</th>
              <th className="text-left py-2.5 px-4 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{t("versionManager.fileCount")}</th>
              <th className="text-left py-2.5 px-4 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{t("versionManager.knowledgeCount")}</th>
              <th className="text-left py-2.5 px-4 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{t("versionManager.createdAt")}</th>
              <th className="text-left py-2.5 px-4 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{t("versionManager.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((version: AnalysisVersion) => (
              <tr
                key={version.version}
                className={`border-b border-[var(--border)]/60 hover:bg-[var(--bg-hover)]/50 transition-colors ${
                  version.isCurrent ? "bg-brand/5" : ""
                }`}
              >
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[var(--text-primary)]">{version.version}</span>
                    {version.isCurrent && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand text-white font-medium">
                        {t("versionManager.current")}
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3 px-4">
                  <StatusBadge status={version.status} />
                </td>
                <td className="py-3 px-4 text-[var(--text-secondary)] tabular-nums">
                  {version.analyzedFiles}/{version.totalFiles}
                </td>
                <td className="py-3 px-4 text-[var(--text-secondary)] tabular-nums">
                  {version.knowledgePointsCount}
                </td>
                <td className="py-3 px-4 text-[var(--text-secondary)]">
                  {formatDate(version.createdAt)}
                </td>
                <td className="py-3 px-4">
                  <div className="flex items-center gap-2">
                    {!version.isCurrent && version.status === "completed" && (
                      <button
                        onClick={() => handleSwitch(version.version)}
                        disabled={switchVersion.isPending}
                        className="px-2.5 py-1 text-[10px] bg-brand text-white rounded-md hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm font-medium"
                      >
                        {t("versionManager.switch")}
                      </button>
                    )}
                    {!version.isCurrent && version.status === "completed" && (
                      <button
                        onClick={() => {
                          setSelectedVersion(version.version);
                          setShowRollbackConfirm(true);
                        }}
                        disabled={rollbackVersion.isPending}
                        className="px-2.5 py-1 text-[10px] bg-status-error text-white rounded-md hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm font-medium"
                      >
                        {t("versionManager.rollback")}
                      </button>
                    )}
                    {version.isCurrent && (
                      <span className="text-xs text-[var(--text-muted)]">{t("versionManager.currentVersion")}</span>
                    )}
                    {version.status !== "completed" && !version.isCurrent && (
                      <span className="text-xs text-[var(--text-muted)]">{t("versionManager.unavailable")}</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showRollbackConfirm && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-50">
          <div className="bg-[var(--bg-card)] rounded-xl border border-[var(--border)] shadow-2xl p-6 max-w-md w-full mx-4">
            <h3 className="text-base font-semibold text-[var(--text-primary)] mb-2">{t("versionManager.confirmRollback")}</h3>
            <p className="text-[var(--text-secondary)] mb-4">
              {t("versionManager.rollbackDesc", { version: selectedVersion })}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowRollbackConfirm(false);
                  setSelectedVersion(null);
                }}
                className="flex-1 px-3 py-2 text-sm rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors font-medium"
              >
                {t("versionManager.cancel")}
              </button>
              <button
                onClick={handleRollback}
                disabled={rollbackVersion.isPending}
                className="flex-1 px-3 py-2 text-sm bg-status-error text-white rounded-md hover:opacity-90 disabled:opacity-50 transition-opacity font-medium shadow-sm"
              >
                {rollbackVersion.isPending ? t("versionManager.rollbacking") : t("versionManager.confirm")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}