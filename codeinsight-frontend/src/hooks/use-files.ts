import { useQuery } from "@tanstack/react-query";
import { getFiles, getFile } from "@/api/files";
import { getAstNodes } from "@/api/ast-nodes";
import { getCallEdges, getCallees, getCallers, getCallChain } from "@/api/call-edges";

/**
 * 文件列表数据钩子
 *
 * 获取指定仓库的文件列表，支持分页。
 */
export function useFiles(repoId: string, page: number = 1, pageSize: number = 100) {
  return useQuery({
    queryKey: ["files", repoId, page, pageSize],
    queryFn: () => getFiles(repoId, page, pageSize),
    enabled: !!repoId,
    staleTime: 5 * 60 * 1000, // 5 分钟缓存
  });
}

/**
 * 单个文件数据钩子
 */
export function useFile(fileId: string | null) {
  return useQuery({
    queryKey: ["file", fileId],
    queryFn: () => getFile(fileId!),
    enabled: !!fileId,
  });
}

/**
 * AST 节点数据钩子
 *
 * 按 file_id 查询该文件的 AST 结构节点。
 */
export function useAstNodes(params: {
  file_id?: string;
  repository_id?: string;
  node_type?: string;
}) {
  return useQuery({
    queryKey: ["ast-nodes", params],
    queryFn: () => getAstNodes(params),
    enabled: !!params.file_id || !!params.repository_id,
    staleTime: 2 * 60 * 1000, // 2 分钟缓存
  });
}

/**
 * 调用边数据钩子
 *
 * 按 file_id 查询该文件的调用边。
 */
export function useCallEdges(params: {
  file_id?: string;
  repository_id?: string;
}) {
  return useQuery({
    queryKey: ["call-edges", params],
    queryFn: () => getCallEdges(params),
    enabled: !!params.file_id || !!params.repository_id,
    staleTime: 2 * 60 * 1000, // 2 分钟缓存
  });
}

/**
 * 获取节点的被调用者（正向调用图）
 */
export function useCallees(nodeId: string | null) {
  return useQuery({
    queryKey: ["callees", nodeId],
    queryFn: () => getCallees(nodeId!),
    enabled: !!nodeId,
    staleTime: 1 * 60 * 1000, // 1 分钟缓存
  });
}

/**
 * 获取节点的调用者（反向调用图）
 */
export function useCallers(nodeId: string | null) {
  return useQuery({
    queryKey: ["callers", nodeId],
    queryFn: () => getCallers(nodeId!),
    enabled: !!nodeId,
    staleTime: 1 * 60 * 1000, // 1 分钟缓存
  });
}

/**
 * 获取调用链（从节点开始的完整调用路径）
 */
export function useCallChain(nodeId: string | null, maxDepth: number = 10) {
  return useQuery({
    queryKey: ["call-chain", nodeId, maxDepth],
    queryFn: () => getCallChain(nodeId!, maxDepth),
    enabled: !!nodeId,
    staleTime: 1 * 60 * 1000, // 1 分钟缓存
  });
}
