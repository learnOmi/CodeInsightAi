"use client";

import { useState, memo } from "react";
import { cn } from "@/utils";
import { getFileIcon } from "@codeinsight/shared";
import type { TreeNode } from "@/utils/tree-utils";

interface TreeNodeProps {
  node: TreeNode;
  level: number;
  selectedFileId?: string;
  onSelectFile: (fileId: string, filePath: string) => void;
}

/** 单个树节点（目录或文件） */
const TreeNodeComponent = memo(function TreeNodeComponent({
  node,
  level,
  selectedFileId,
  onSelectFile,
}: TreeNodeProps) {
  const [expanded, setExpanded] = useState(level < 2); // 默认展开前两层

  const handleClick = () => {
    if (node.isDirectory) {
      setExpanded((prev) => !prev);
    } else if (node.id) {
      onSelectFile(node.id, node.path);
    }
  };

  const isSelected = !node.isDirectory && node.id === selectedFileId;

  return (
    <div>
      <div
        onClick={handleClick}
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
            {expanded ? "\u25BE" : "\u25B8"}
          </span>
        ) : (
          <span className="w-3 flex-shrink-0" />
        )}

        {/* 图标 */}
        <span className="flex-shrink-0">
          {node.isDirectory ? (expanded ? "\uD83D\uDCC2" : "\uD83D\uDCC1") : getFileIcon(node.name)}
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
            />
          ))}
        </div>
      )}
    </div>
  );
});

interface FileTreeProps {
  nodes: TreeNode[];
  selectedFileId?: string;
  onSelectFile: (fileId: string, filePath: string) => void;
}

/** 文件树视图 */
export function FileTree({ nodes, selectedFileId, onSelectFile }: FileTreeProps) {
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
        />
      ))}
    </div>
  );
}
