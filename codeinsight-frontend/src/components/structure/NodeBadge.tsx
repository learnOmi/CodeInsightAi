"use client";

import { cn } from "@/utils";
import { getNodeTypeConfig } from "@codeinsight/shared";

/** AST 节点类型标签 */
export function NodeBadge({ type, name }: { type: string; name: string }) {
  const config = getNodeTypeConfig(type);

  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={cn(
          "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-xs font-medium",
          config.color
        )}
      >
        {config.icon}
        {config.label}
      </span>
      <span className="font-mono text-sm text-gray-800">{name}</span>
    </span>
  );
}
