/**
 * 结构概览工具函数
 *
 * 处理 AST 节点的层级分组和展示逻辑。
 */

import type { AstNodeItem } from "@/api/ast-nodes";

export interface GroupedNode extends AstNodeItem {
  depth: number;
  children: GroupedNode[];
}

/**
 * 基于行号范围推断父子关系，将 AST 节点分组为树形结构
 *
 * 优先使用 parentNodeId（数据库存储的显式父子关系），
 * 若大量节点无 parentNodeId 则按 startLine/startColumn/endLine 推断层级。
 *
 * 推断策略：
 *  - 按 (startLine, startColumn) 升序排列
 *  - 利用栈维护当前节点的可候选父节点
 *  - 候选父节点 endLine < 当前 startLine → 出栈（不再包含当前节点）
 *  - 栈顶 = 最近的仍包含当前节点的节点 → 即为父节点
 */
export function groupAstNodes(nodes: AstNodeItem[]): GroupedNode[] {
  const nodeMap = new Map<string, GroupedNode>();
  for (const node of nodes) {
    nodeMap.set(node.id, { ...node, depth: 0, children: [] });
  }

  // —— 优先走 parentNodeId ——
  const roots: GroupedNode[] = [];
  let orphans = 0;
  let total = 0;
  for (const node of nodes) {
    total++;
    const grouped = nodeMap.get(node.id)!;
    if (node.parentNodeId && nodeMap.has(node.parentNodeId)) {
      const parent = nodeMap.get(node.parentNodeId)!;
      parent.children.push(grouped);
    } else {
      if (!node.parentNodeId) orphans++;
      roots.push(grouped);
    }
  }

  // 大部分节点有 parentNodeId → 直接用，不用推断
  if (orphans < total * 0.5) {
    return assignDepth(roots, 0);
  }

  // —— 大量节点无 parentNodeId → 按行号范围推断层级 ——
  // 清空之前的父子关系
  for (const node of nodes) {
    const grouped = nodeMap.get(node.id)!;
    grouped.children = [];
  }

  // 按 (startLine, startColumn) 升序，endLine 降序（宽范围优先做父节点）
  const sorted = [...nodes].sort((a, b) => {
    if (a.startLine !== b.startLine) return a.startLine - b.startLine;
    const colA = a.startColumn ?? 0;
    const colB = b.startColumn ?? 0;
    if (colA !== colB) return colA - colB;
    return (b.endLine - b.startLine) - (a.endLine - a.startLine); // 更宽的优先
  });

  const inferredRoots: GroupedNode[] = [];
  const stack: GroupedNode[] = [];

  for (const node of sorted) {
    const grouped = nodeMap.get(node.id)!;
    // 弹出不再包含当前节点的候选父节点
    while (stack.length > 0) {
      const top = stack[stack.length - 1];
      if (top.endLine < node.startLine || (top.endLine === node.startLine && top.endColumn != null && node.startColumn != null && top.endColumn <= node.startColumn)) {
        stack.pop();
      } else {
        break;
      }
    }

    if (stack.length > 0) {
      stack[stack.length - 1].children.push(grouped);
    } else {
      inferredRoots.push(grouped);
    }
    stack.push(grouped);
  }

  return assignDepth(inferredRoots, 0);
}

function assignDepth(nodes: GroupedNode[], depth: number): GroupedNode[] {
  for (const node of nodes) {
    node.depth = depth;
    assignDepth(node.children, depth + 1);
  }
  return nodes;
}

/**
 * 将树形结构扁平化为列表（用于顺序渲染）
 *
 * 按深度优先遍历，保留 depth 信息。
 */
export function flattenGroupedNodes(nodes: GroupedNode[]): GroupedNode[] {
  const result: GroupedNode[] = [];

  function traverse(node: GroupedNode) {
    result.push(node);
    for (const child of node.children) {
      traverse(child);
    }
  }

  for (const node of nodes) {
    traverse(node);
  }

  return result;
}
