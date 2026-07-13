/**
 * 文件树构建工具
 *
 * 将扁平的文件列表转换为树形结构，供 FileTree 组件使用。
 */

import type { FileItem } from "@/api/files";

export interface TreeNode {
  id?: string;
  path: string;
  name: string;
  children: TreeNode[];
  isDirectory: boolean;
  file?: FileItem;
}

/**
 * 将扁平文件列表构建为树形结构
 *
 * 算法：按 path 的 "/" 分隔符逐层构建目录树
 */
export function buildFileTree(files: FileItem[]): TreeNode[] {
  const root: TreeNode = { path: "", name: "", children: [], isDirectory: true };

  for (const file of files) {
    const parts = file.path.split("/").filter(Boolean);
    let current = root;

    // 逐层遍历目录部分
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      const childPath = current.path ? `${current.path}/${part}` : part;

      let child = current.children.find((c) => c.name === part && c.isDirectory);
      if (!child) {
        child = {
          path: childPath,
          name: part,
          children: [],
          isDirectory: true,
        };
        current.children.push(child);
      }
      current = child;
    }

    // 添加文件节点
    const fileName = parts[parts.length - 1] ?? file.path;
    current.children.push({
      id: file.id,
      path: file.path,
      name: fileName,
      children: [],
      isDirectory: false,
      file,
    });
  }

  return sortChildren(root.children);
}

/**
 * 排序子节点：目录优先，然后按字母排序
 */
function sortChildren(children: TreeNode[]): TreeNode[] {
  return children.sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) {
      return a.isDirectory ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });
}

/**
 * 统计树中的文件总数
 */
export function countFiles(nodes: TreeNode[]): number {
  let count = 0;
  for (const node of nodes) {
    if (node.isDirectory) {
      count += countFiles(node.children);
    } else {
      count++;
    }
  }
  return count;
}

/**
 * 在树中查找指定 id 的节点
 */
export function findNodeById(nodes: TreeNode[], id: string): TreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children.length > 0) {
      const found = findNodeById(node.children, id);
      if (found) return found;
    }
  }
  return null;
}
