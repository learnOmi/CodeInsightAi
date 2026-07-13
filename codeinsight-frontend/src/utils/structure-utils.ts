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
 * 按 parent_node_id 将 AST 节点分组为树形结构
 *
 * 无 parent_node_id 的节点为根节点，
 * 其余节点按其 parent_node_id 归入对应父节点的 children 列表。
 */
export function groupAstNodes(nodes: AstNodeItem[]): GroupedNode[] {
  const nodeMap = new Map<string, GroupedNode>();
  const roots: GroupedNode[] = [];

  // 第一遍：创建所有节点的映射
  for (const node of nodes) {
    nodeMap.set(node.id, { ...node, depth: 0, children: [] });
  }

  // 第二遍：建立父子关系
  for (const node of nodes) {
    const grouped = nodeMap.get(node.id)!;
    if (node.parentNodeId && nodeMap.has(node.parentNodeId)) {
      const parent = nodeMap.get(node.parentNodeId)!;
      parent.children.push(grouped);
    } else {
      roots.push(grouped);
    }
  }

  // 计算深度
  function setDepth(node: GroupedNode, depth: number) {
    node.depth = depth;
    for (const child of node.children) {
      setDepth(child, depth + 1);
    }
  }

  for (const root of roots) {
    setDepth(root, 0);
  }

  return roots;
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
