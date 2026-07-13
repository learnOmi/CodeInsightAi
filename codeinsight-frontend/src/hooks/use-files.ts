import { useQuery } from "@tanstack/react-query";
import { getFiles, getFile } from "@/api/files";
import { getAstNodes } from "@/api/ast-nodes";

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
