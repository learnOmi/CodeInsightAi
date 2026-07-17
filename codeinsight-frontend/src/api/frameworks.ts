import { apiFetch } from "./base";

/** 框架检测结果 */
export interface FrameworkPattern {
  id: string;
  repositoryId: string;
  analysisVersionId: string | null;
  framework: string;
  category: string;
  confidence: number;
  evidence: Record<string, unknown>;
  detectedAt: string;
}

/** 获取仓库检测到的框架列表 */
export async function getFrameworks(
  repositoryId: string,
  params?: {
    category?: string;
    minConfidence?: number;
  }
): Promise<FrameworkPattern[]> {
  const searchParams = new URLSearchParams();
  if (params?.category) searchParams.set("category", params.category);
  if (params?.minConfidence !== undefined) {
    searchParams.set("min_confidence", String(params.minConfidence));
  }
  const query = searchParams.toString();
  return apiFetch(
    `/api/v1/repositories/${repositoryId}/frameworks${query ? `?${query}` : ""}`
  );
}

/** 获取仓库检测到的框架数量统计 */
export async function getFrameworksCount(
  repositoryId: string
): Promise<{ count: number }> {
  return apiFetch(
    `/api/v1/repositories/${repositoryId}/frameworks/count`
  );
}
