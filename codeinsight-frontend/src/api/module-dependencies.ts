import { apiFetch } from "./base";

/** 模块依赖项 */
export interface ModuleDependency {
  id: string;
  repositoryId: string;
  importerFileId: string;
  importedFileId: string | null;
  importName: string;
  importType: string;
  createdAt: string;
}

/** 模块依赖统计 */
export interface ModuleDependencyStats {
  total: number;
  internal: number;
  external: number;
  byType: Record<string, number>;
}

/** 获取仓库的所有模块依赖 */
export async function getModuleDependencies(
  repositoryId: string
): Promise<ModuleDependency[]> {
  const result = await apiFetch<ModuleDependency[]>(`/api/v1/repositories/${repositoryId}/module-dependencies`);
  
  if (Array.isArray(result)) {
    return result.map((dep) => ({
      ...dep,
      importedFileId: dep.importedFileId === "None" ? null : dep.importedFileId,
    }));
  }
  
  if (result && typeof result === "object" && "value" in result) {
    return (result as { value: ModuleDependency[] }).value.map((dep) => ({
      ...dep,
      importedFileId: dep.importedFileId === "None" ? null : dep.importedFileId,
    }));
  }
  
  return [];
}

/** 获取模块依赖数量 */
export async function getModuleDependenciesCount(
  repositoryId: string
): Promise<{ count: number }> {
  return apiFetch(`/api/v1/repositories/${repositoryId}/module-dependencies/count`);
}

/** 获取模块依赖统计 */
export async function getModuleDependencyStats(
  repositoryId: string
): Promise<ModuleDependencyStats> {
  return apiFetch(`/api/v1/repositories/${repositoryId}/module-dependencies/stats`);
}
