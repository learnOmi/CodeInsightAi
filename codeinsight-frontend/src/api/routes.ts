import { apiFetch } from "./base";

/** API 路由项 */
export interface ApiRoute {
  id: string;
  repositoryId: string;
  analysisVersionId: string | null;
  astNodeId: string | null;
  httpMethod: string;
  pathPattern: string;
  handlerFunction: string;
  handlerFile: string;
  middlewares: RouteMiddleware[];
  framework: string;
  createdAt: string;
}

/** 中间件信息 */
export interface RouteMiddleware {
  name: string;
  order: number;
  file: string;
  type: string;
}

/** 获取仓库的 API 路由列表 */
export async function getRoutes(
  repositoryId: string,
  params?: {
    httpMethod?: string;
    framework?: string;
    pathPattern?: string;
  }
): Promise<ApiRoute[]> {
  const searchParams = new URLSearchParams();
  if (params?.httpMethod) searchParams.set("http_method", params.httpMethod);
  if (params?.framework) searchParams.set("framework", params.framework);
  if (params?.pathPattern) searchParams.set("path_pattern", params.pathPattern);
  const query = searchParams.toString();
  return apiFetch(
    `/api/v1/repositories/${repositoryId}/routes${query ? `?${query}` : ""}`
  );
}

/** 获取仓库的 API 路由数量统计 */
export async function getRoutesCount(
  repositoryId: string
): Promise<{ count: number }> {
  return apiFetch(`/api/v1/repositories/${repositoryId}/routes/count`);
}
