import { apiFetch } from "./base";
import type { components } from "@codeinsight/shared";

type KnowledgePoint = components["schemas"]["KnowledgePoint"];
type PaginatedKnowledgePoints = components["schemas"]["PaginatedKnowledgePoints"];
type KnowledgeStats = components["schemas"]["KnowledgeStats"];

export interface ListKnowledgePointsParams {
  repositoryId: string;
  version?: string;
  category?: string;
  tag?: string;
  page?: number;
  pageSize?: number;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
}

/** 获取知识点列表 */
export async function getKnowledgePoints(
  params: ListKnowledgePointsParams
): Promise<PaginatedKnowledgePoints> {
  const searchParams = new URLSearchParams({
    repository_id: params.repositoryId,
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
    sort_by: params.sortBy ?? "created_at",
    sort_order: params.sortOrder ?? "desc",
  });
  if (params.version) searchParams.set("version", params.version);
  if (params.category) searchParams.set("category", params.category);
  if (params.tag) searchParams.set("tag", params.tag);

  return apiFetch(`/api/v1/knowledge-points?${searchParams.toString()}`);
}

/** 获取知识点详情 */
export async function getKnowledgePoint(id: string): Promise<KnowledgePoint> {
  return apiFetch(`/api/v1/knowledge-points/${id}`);
}

/** 获取知识点统计 */
export async function getKnowledgeStats(
  repositoryId: string,
  version?: string
): Promise<KnowledgeStats> {
  const searchParams = new URLSearchParams();
  if (version) searchParams.set("version", version);
  const query = searchParams.toString();
  return apiFetch(
    `/api/v1/repositories/${repositoryId}/knowledge-stats${query ? `?${query}` : ""}`
  );
}