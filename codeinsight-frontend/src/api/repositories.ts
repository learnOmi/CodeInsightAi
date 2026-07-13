import { apiFetch } from "./base";
import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];
type RepositoryCreate = components["schemas"]["RepositoryCreate"];
type RepositoryUpdate = components["schemas"]["RepositoryUpdate"];
type AnalysisTask = components["schemas"]["AnalysisTask"];
type AnalyzeRequest = components["schemas"]["AnalyzeRequest"];

/** 获取仓库列表 */
export async function getRepositories(): Promise<Repository[]> {
  return apiFetch("/api/v1/repositories");
}

/** 获取单个仓库 */
export async function getRepository(id: string): Promise<Repository> {
  return apiFetch(`/api/v1/repositories/${id}`);
}

/** 创建仓库 */
export async function createRepository(data: RepositoryCreate): Promise<Repository> {
  return apiFetch("/api/v1/repositories", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/** 更新仓库 */
export async function updateRepository(id: string, data: RepositoryUpdate): Promise<Repository> {
  return apiFetch(`/api/v1/repositories/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/** 删除仓库 */
export async function deleteRepository(id: string): Promise<void> {
  return apiFetch(`/api/v1/repositories/${id}`, {
    method: "DELETE",
  });
}

/** 提交分析任务 */
export async function submitAnalysis(
  repositoryId: string,
  data?: AnalyzeRequest
): Promise<AnalysisTask> {
  return apiFetch(`/api/v1/repositories/${repositoryId}/analyze`, {
    method: "POST",
    body: data ? JSON.stringify(data) : undefined,
  });
}

/** 获取任务状态 */
export async function getTaskStatus(taskId: string): Promise<AnalysisTask> {
  return apiFetch(`/api/v1/tasks/${taskId}`);
}

/** 取消任务 */
export async function cancelTask(taskId: string): Promise<void> {
  return apiFetch(`/api/v1/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}
