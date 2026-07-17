import { apiFetch } from "./base";

/** 仓库全局统计信息 */
export interface RepositoryStats {
  fileCount: number;
  totalLines: number;
  languageDistribution: Record<string, number>;
  nodeCount: number;
  nodeTypeDistribution: Record<string, number>;
  edgeCount: number;
  edgeTypeDistribution: Record<string, number>;
  moduleDependencyCount: number;
  externalDependencyCount: number;
  ecosystemDistribution: Record<string, number>;
  frameworkCount: number;
  routeCount: number;
}

/** 获取仓库统计信息 */
export async function getRepositoryStats(
  repositoryId: string
): Promise<RepositoryStats> {
  return apiFetch(`/api/v1/repositories/${repositoryId}/stats`);
}
