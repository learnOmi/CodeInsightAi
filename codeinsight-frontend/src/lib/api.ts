import type { components } from "@codeinsight/shared";

type Repository = components["schemas"]["Repository"];
type RepositoryCreate = components["schemas"]["RepositoryCreate"];
type RepositoryUpdate = components["schemas"]["RepositoryUpdate"];
type AnalysisTask = components["schemas"]["AnalysisTask"];
type AnalyzeRequest = components["schemas"]["AnalyzeRequest"];

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  options: globalThis.RequestInit = {}
): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new APIError(response.status, errorBody.detail || errorBody.message || "API request failed");
  }

  return response.json();
}

export class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "APIError";
  }
}

export async function getRepositories(): Promise<Repository[]> {
  return apiFetch("/api/v1/repositories");
}

export async function getRepository(id: string): Promise<Repository> {
  return apiFetch(`/api/v1/repositories/${id}`);
}

export async function createRepository(data: RepositoryCreate): Promise<Repository> {
  return apiFetch("/api/v1/repositories", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateRepository(id: string, data: RepositoryUpdate): Promise<Repository> {
  return apiFetch(`/api/v1/repositories/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteRepository(id: string): Promise<void> {
  return apiFetch(`/api/v1/repositories/${id}`, {
    method: "DELETE",
  });
}

export async function submitAnalysis(
  repositoryId: string,
  data?: AnalyzeRequest
): Promise<AnalysisTask> {
  return apiFetch(`/api/v1/repositories/${repositoryId}/analyze`, {
    method: "POST",
    body: data ? JSON.stringify(data) : undefined,
  });
}

export async function getTaskStatus(taskId: string): Promise<AnalysisTask> {
  return apiFetch(`/api/v1/tasks/${taskId}`);
}

export async function cancelTask(taskId: string): Promise<void> {
  return apiFetch(`/api/v1/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}