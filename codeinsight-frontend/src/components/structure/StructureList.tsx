"use client";

import { useMemo } from "react";
import { useAstNodes } from "@/hooks/use-files";
import { groupAstNodes, flattenGroupedNodes } from "@/utils/structure-utils";
import { FrameworkBadge } from "@/components/common/FrameworkBadge";
import { NodeBadge } from "./NodeBadge";

interface StructureListProps {
  fileId: string;
  fileName: string;
}

/** 代码结构概览列表 */
export function StructureList({ fileId, fileName }: StructureListProps) {
  const { data: nodes, isLoading, error } = useAstNodes({ file_id: fileId });

  const flatNodes = useMemo(() => {
    if (!nodes) return [];
    // 去重：按 (start_line, start_column, node_type, name) 去重，保留最新记录
    const seen = new Set<string>();
    const deduped: typeof nodes = [];
    for (const node of nodes) {
      const key = `${node.startLine}_${node.startColumn}_${node.nodeType}_${node.name}`;
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push(node);
      }
    }
    const grouped = groupAstNodes(deduped);
    return flattenGroupedNodes(grouped);
  }, [nodes]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <h3 className="text-lg font-semibold mb-3 text-[var(--text-primary)]">{fileName}</h3>
        {[...Array(8)].map((_, i) => (
          <div key={i} className="h-6 bg-[var(--bg-hover)] rounded animate-pulse" style={{ width: `${80 - i * 5}%` }} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <h3 className="text-lg font-semibold mb-3 text-[var(--text-primary)]">{fileName}</h3>
        <div className="text-red-500 text-sm">加载结构数据失败</div>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-lg font-semibold mb-3 text-[var(--text-primary)]">{fileName}</h3>

      {flatNodes.length === 0 ? (
        <div className="text-[var(--text-muted)] text-sm py-4">
          该文件暂无解析结果
        </div>
      ) : (
        <ul className="space-y-0.5">
          {flatNodes.map((node) => {
            // 后端 tags 字段类型为 list（unknown[]），此处安全过滤为 string[]
            const tags = Array.isArray(node.tags)
              ? node.tags.filter((t): t is string => typeof t === "string")
              : [];
            return (
              <li
                key={node.id}
                className="flex items-center gap-2 py-1 px-2 rounded hover:bg-[var(--bg-hover)] transition-colors"
                style={{ paddingLeft: `${node.depth * 20 + 8}px` }}
              >
                <NodeBadge type={node.nodeType} name={node.name} />
                {tags.length > 0 && <FrameworkBadge tags={tags} />}
                <span className="ml-auto text-xs text-[var(--text-muted)] font-mono flex-shrink-0">
                  L{node.startLine}-{node.endLine}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
