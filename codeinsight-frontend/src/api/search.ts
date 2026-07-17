import { apiFetch } from "./base";

/** 搜索到的 AST 节点 */
export interface SearchNodeResult {
  id: string;
  repositoryId: string;
  fileId: string;
  nodeType: string;
  name: string;
  filePath: string;
  language: string;
  qualifiedName: string | null;
  startLine: number;
  endLine: number;
  tags: string[];
}

/** 搜索到的文件 */
export interface SearchFileResult {
  id: string;
  repositoryId: string;
  path: string;
  language: string;
  lineCount: number;
}

/** 搜索建议项 */
export interface SearchSuggestion {
  text: string;
  type: string;
  count: number;
}

/** 搜索 AST 节点 */
export async function searchNodes(params: {
  q: string;
  repository_id?: string;
  node_type?: string;
  limit?: number;
}): Promise<SearchNodeResult[]> {
  const sp = new URLSearchParams();
  sp.set("q", params.q);
  if (params.repository_id) sp.set("repository_id", params.repository_id);
  if (params.node_type) sp.set("node_type", params.node_type);
  if (params.limit) sp.set("limit", String(params.limit));
  return apiFetch(`/api/v1/search/nodes?${sp.toString()}`);
}

/** 搜索文件 */
export async function searchFiles(params: {
  q: string;
  repository_id?: string;
  limit?: number;
}): Promise<SearchFileResult[]> {
  const sp = new URLSearchParams();
  sp.set("q", params.q);
  if (params.repository_id) sp.set("repository_id", params.repository_id);
  if (params.limit) sp.set("limit", String(params.limit));
  return apiFetch(`/api/v1/search/files?${sp.toString()}`);
}

/** 搜索建议 */
export async function searchSuggestions(
  q: string,
  repository_id?: string,
  limit?: number
): Promise<{ query: string; suggestions: SearchSuggestion[] }> {
  const sp = new URLSearchParams();
  sp.set("q", q);
  if (repository_id) sp.set("repository_id", repository_id);
  if (limit) sp.set("limit", String(limit));
  return apiFetch(`/api/v1/search/suggestions?${sp.toString()}`);
}
