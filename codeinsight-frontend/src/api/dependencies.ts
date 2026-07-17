import { apiFetch } from "./base";

/** 外部依赖项 */
export interface ExternalDependency {
  id: string;
  repositoryId: string;
  analysisVersionId: string | null;
  ecosystem: string;
  groupName: string | null;
  artifactName: string;
  version: string | null;
  versionRange: string | null;
  scope: string;
  declarationFile: string | null;
  usedByFiles: string[];
  createdAt: string;
}

/** 获取仓库的外部依赖列表 */
export async function getDependencies(
  repositoryId: string,
  params?: {
    ecosystem?: string;
    scope?: string;
  }
): Promise<ExternalDependency[]> {
  const searchParams = new URLSearchParams();
  if (params?.ecosystem) searchParams.set("ecosystem", params.ecosystem);
  if (params?.scope) searchParams.set("scope", params.scope);
  const query = searchParams.toString();
  return apiFetch(
    `/api/v1/repositories/${repositoryId}/dependencies${query ? `?${query}` : ""}`
  );
}

/** 获取仓库的外部依赖数量统计 */
export async function getDependenciesCount(
  repositoryId: string
): Promise<{ count: number }> {
  return apiFetch(
    `/api/v1/repositories/${repositoryId}/dependencies/count`
  );
}
