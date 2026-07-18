"use client";

import { cn } from "@/utils";
import { getAnalysisStatusConfig } from "@codeinsight/shared";

/** 分析状态徽标 */
export function StatusBadge({ status, variant = "default" }: { status: string; variant?: "default" | "compact" }) {
  const config = getAnalysisStatusConfig(status);

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
      {config.label}
    </span>
  );
}