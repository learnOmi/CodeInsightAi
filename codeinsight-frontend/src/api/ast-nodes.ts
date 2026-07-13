import { apiFetch } from "./base";
import type { components } from "@codeinsight/shared";

type AstNodeItem = components["schemas"]["AstNode"];
export type { AstNodeItem };

/** 获取 AST 节点列表 */
export async function getAstNodes(params: {
  file_id?: string;
  repository_id?: string;
  node_type?: string;
}): Promise<AstNodeItem[]> {
  const searchParams = new URLSearchParams();
  if (params.file_id) searchParams.set("file_id", params.file_id);
  if (params.repository_id) searchParams.set("repository_id", params.repository_id);
  if (params.node_type) searchParams.set("node_type", params.node_type);
  const query = searchParams.toString();
  return apiFetch(`/api/v1/ast-nodes${query ? `?${query}` : ""}`);
}
