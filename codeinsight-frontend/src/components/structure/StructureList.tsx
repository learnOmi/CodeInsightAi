"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { useAstNodes } from "@/hooks/use-files";
import { groupAstNodes, flattenGroupedNodes } from "@/utils/structure-utils";
import { FrameworkBadge } from "@/components/common/FrameworkBadge";
import { NodeBadge } from "./NodeBadge";
import type { NavigableProps } from "@/components/analysis/NavTrailBar";

export interface FlatNode {
  id: string;
  depth: number;
  nodeType: string;
  name: string;
  startLine: number;
  endLine: number;
  signature?: string | null;
  annotations?: unknown[];
  tags?: unknown[];
}

interface StructureListProps extends NavigableProps {
  fileId: string;
  fileName: string;
  highlightNodeId?: string;
}

/** 代码结构概览列表 */
export function StructureList({ fileId, fileName, onNavigate, highlightNodeId }: StructureListProps) {
  const { data: nodes, isLoading, error } = useAstNodes({ file_id: fileId });
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map());

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

  useEffect(() => {
    if (highlightNodeId && flatNodes.length > 0) {
      const nodeElement = nodeRefs.current.get(highlightNodeId);
      if (nodeElement) {
        nodeElement.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }, [highlightNodeId, flatNodes]);

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
            const hasDetails = node.signature || (node.annotations && node.annotations.length > 0);
            return (
              <StructureNode
                key={node.id}
                node={node}
                tags={tags}
                hasDetails={!!hasDetails}
                onNavigate={onNavigate}
                setRef={(el) => { if (el) nodeRefs.current.set(node.id, el); }}
                isHighlighted={highlightNodeId === node.id}
              />
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** 单个结构节点行（支持展开签名与注解详情） */
function StructureNode({
  node,
  tags,
  hasDetails,
  onNavigate,
  setRef,
  isHighlighted,
}: {
  node: FlatNode;
  tags: string[];
  hasDetails: boolean;
  onNavigate?: NavigableProps["onNavigate"];
  setRef?: (el: HTMLDivElement) => void;
  isHighlighted?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <li>
      <div
        ref={setRef}
        className={`flex items-center gap-2 py-1 px-2 rounded hover:bg-[var(--bg-hover)] transition-colors cursor-pointer ${
          isHighlighted ? "bg-blue-100 ring-1 ring-blue-400" : ""
        }`}
        style={{ paddingLeft: `${node.depth * 20 + 8}px` }}
        onClick={() => hasDetails && setExpanded(!expanded)}
      >
        <NodeBadge type={node.nodeType} name={node.name} />
        {tags.length > 0 && <FrameworkBadge tags={tags} />}
        <span className="ml-auto text-xs text-[var(--text-muted)] font-mono flex-shrink-0">
          L{node.startLine}-{node.endLine}
        </span>
        {(node.nodeType === "function" || node.nodeType === "method") && onNavigate && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onNavigate({ component: "callgraph", nodeId: node.id, label: node.name, detail: "调用图" });
            }}
            className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors flex-shrink-0"
            title="查看调用图"
          >
            ⊙调用图
          </button>
        )}
        {hasDetails && (
          <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0">
            {expanded ? "▲" : "▼"}
          </span>
        )}
      </div>

      {/* 展开详情：signature + annotations */}
      {expanded && (
        <div
          className="px-2 py-1 space-y-1 text-xs border-l-2 border-[var(--border)] ml-[18px] pl-3 mb-1"
          style={{ marginLeft: `${node.depth * 20 + 26}px` }}
        >
          {node.signature && (
            <div className="font-mono text-[var(--text-muted)]">
              <span className="text-[10px] text-[var(--text-muted)] font-semibold mr-1">签名:</span>
              {node.signature}
            </div>
          )}
          {node.annotations && node.annotations.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <span className="text-[10px] text-[var(--text-muted)] font-semibold">注解:</span>
              {node.annotations.map((ann: unknown, idx: number) => {
                const annObj = ann as { name?: string };
                return (
                  <span
                    key={idx}
                    className="inline-flex items-center rounded px-1 py-0.5 text-[10px] font-mono bg-yellow-100 text-yellow-700"
                  >
                    {annObj.name || String(ann)}
                  </span>
                );
              })}
            </div>
          )}
        </div>
      )}
    </li>
  );
}
