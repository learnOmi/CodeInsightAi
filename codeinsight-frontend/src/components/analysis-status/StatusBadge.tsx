"use client";

import { cn } from "@/utils";
import { getAnalysisStatusConfig } from "@codeinsight/shared";

/** 分析状态徽标 */
export function StatusBadge({ status }: { status: string }) {
  const config = getAnalysisStatusConfig(status);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium",
        config.color,
        config.animate && "animate-pulse"
      )}
    >
      <span className={config.animate ? "inline-block animate-spin" : ""}>
        {config.icon}
      </span>
      {config.label}
    </span>
  );
}
