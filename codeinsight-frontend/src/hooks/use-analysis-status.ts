import { useQuery } from "@tanstack/react-query";
import { getRepository } from "@/api/repositories";
import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];

/**
 * 仓库分析状态钩子
 *
 * 获取仓库当前状态（待分析/分析中/已完成/失败），
 * 分析中时自动轮询，完成后停止。
 */
export function useAnalysisStatus(repoId: string) {
  return useQuery<Repository>({
    queryKey: ["repositories", repoId, "status"],
    queryFn: () => getRepository(repoId),
    enabled: !!repoId,
    staleTime: 30 * 1000, // 30 秒缓存
    refetchInterval: (query) => {
      // Stop polling on 401 (token expired)
      if (query.state.error && (query.state.error as any)?.response?.status === 401) {
        return false;
      }
      const data = query.state.data;
      // 分析中时每 10 秒轮询，否则停止
      return data?.status === "analyzing" ? 10_000 : undefined;
    },
  });
}
