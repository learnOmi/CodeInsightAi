"use client";

import React, { useState, memo } from "react";
import { cn } from "@/utils";
import { getFileIcon } from "@codeinsight/shared";
import type { TreeNode } from "@/utils/tree-utils";
import type { NavigableProps } from "@/components/analysis/NavTrailBar";

interface TreeNodeProps {
  node: TreeNode;
  level: number;
  selectedFileId?: string;
  onSelectFile: (fileId: string, filePath: string) => void;
  onNavigate?: NavigableProps["onNavigate"];
}

/** 单个树节点（目录或文件） */
const TreeNodeComponent = memo(function TreeNodeComponent({
  node,
  level,
  selectedFileId,
  onSelectFile,
  onNavigate,
}: TreeNodeProps) {
  const [expanded, setExpanded] = useState(level < 2); // 默认展开前两层
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);

  const handleClick = () => {
    setContextMenu(null);
    if (node.isDirectory) {
      setExpanded((prev) => !prev);
    } else if (node.id) {
      onSelectFile(node.id, node.path);
    }
  };

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!node.isDirectory && node.id && onNavigate) {
      setContextMenu({ x: e.clientX, y: e.clientY });
    }
  };

  const handleMenuAction = (component: "structure" | "callgraph") => {
    if (node.id) {
      onNavigate!({ component, fileId: node.id, label: node.name, detail: component === "structure" ? "代码结构" : "调用图" });
    }
    setContextMenu(null);
  };

  const isSelected = !node.isDirectory && node.id === selectedFileId;

  return (
    <div>
      <div
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        className={cn(
          "flex items-center gap-1.5 py-1 px-2 rounded cursor-pointer text-sm transition-colors",
          "hover:bg-[var(--bg-hover)]",
          isSelected && "bg-blue-50 text-blue-700 font-medium"
        )}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
      >
        {/* 展开/折叠箭头 */}
        {node.isDirectory ? (
          <span className="text-[var(--text-muted)] text-xs w-3 flex-shrink-0">
            {expanded ? "▾" : "▸"}
          </span>
        ) : (
          <span className="w-3 flex-shrink-0" />
        )}

        {/* 图标 */}
        <span className="flex-shrink-0">
          {node.isDirectory ? (expanded ? "📂" : "📁") : getFileIcon(node.name)}
        </span>

        {/* 名称 */}
        <span className="truncate text-[var(--text-primary)]">{node.name}</span>

        {/* 行数（仅文件显示） */}
        {!node.isDirectory && node.file && (
          <span className="ml-auto text-xs text-[var(--text-muted)] flex-shrink-0">
            {node.file.lineCount}L
          </span>
        )}
      </div>

      {/* 子节点 */}
      {node.isDirectory && expanded && node.children.length > 0 && (
        <div>
          {node.children.map((child) => (
            <TreeNodeComponent
              key={child.id ?? child.path}
              node={child}
              level={level + 1}
              selectedFileId={selectedFileId}
              onSelectFile={onSelectFile}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}

      {contextMenu && (
        <>
          <div className="fixed inset-0 z-50" onClick={() => setContextMenu(null)} />
          <div
            className="fixed z-50 bg-[var(--bg-card)] border border-[var(--border)] rounded-lg shadow-xl py-1 min-w-[140px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <button
              onClick={() => handleMenuAction("structure")}
              className="w-full text-left px-3 py-1.5 text-sm text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              ◆ 查看代码结构
            </button>
            <button
              onClick={() => handleMenuAction("callgraph")}
              className="w-full text-left px-3 py-1.5 text-sm text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              ⊙ 查看调用图
            </button>
          </div>
        </>
      )}
    </div>
  );
});

interface FileTreeProps {
  nodes: TreeNode[];
  selectedFileId?: string;
  onSelectFile: (fileId: string, filePath: string) => void;
  onNavigate?: NavigableProps["onNavigate"];
}

/** 文件树视图 */
export function FileTree({ nodes, selectedFileId, onSelectFile, onNavigate }: FileTreeProps) {
  if (nodes.length === 0) {
    return (
      <div className="text-center text-[var(--text-muted)] text-sm py-8">
        暂无文件
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {nodes.map((node) => (
        <TreeNodeComponent
          key={node.id ?? node.path}
          node={node}
          level={0}
          selectedFileId={selectedFileId}
          onSelectFile={onSelectFile}
          onNavigate={onNavigate}
        />
      ))}
    </div>
  );
}
