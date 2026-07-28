"use client";

import { useTranslation } from "react-i18next";
import { cn } from "@/utils";
import { getAnalysisStatusConfig } from "@codeinsight/shared";

/** 分析状态徽标 */
export function StatusBadge({ status, variant = "default" }: { status: string; variant?: "default" | "compact" }) {
  const { t } = useTranslation();
  const config = getAnalysisStatusConfig(status);

  const STATUS_KEY_MAP: Record<string, string> = {
    pending: "repoCard.step.pending",
    analyzing: "repoCard.step.analyzing",
    scanning: "repoCard.step.scanning",
    parsing: "repoCard.step.parsing",
    analyzing_structures: "repoCard.step.analyzingStructures",
    analyzing_modules: "repoCard.step.analyzingModules",
    storing: "repoCard.step.storing",
    completed: "repoCard.step.completed",
    failed: "repoCard.step.failed",
    cancelled: "repoCard.step.cancelled",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-semibold tracking-wide",
        variant === "compact" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs",
        config.color,
        config.animate && "animate-pulse"
      )}
    >
      <span className={`w-1.5 h-1.5 rounded-full`} style={{ backgroundColor: "currentColor" }} />
      {t(STATUS_KEY_MAP[status] || "repoCard.step.pending")}
    </span>
  );
}