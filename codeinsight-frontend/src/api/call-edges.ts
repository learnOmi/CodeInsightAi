import { apiFetch } from "./base";

export interface CallEdge {
  id: string;
  repositoryId: string;
  callerNodeId: string;
  calleeNodeId: string | null;
  startLine: number;
  startColumn: number;
  callName: string;
  callType: "static" | "dynamic" | "unknown";
  createdAt: string;
}

export interface CallEdgeWithNode {
  edgeId: string;
  callName: string;
  callType: "static" | "dynamic" | "unknown";
  startLine: number;
  startColumn: number;
  caller?: {
    id: string;
    name: string;
    nodeType: string;
    fileId?: string;
    filePath: string;
  };
  callee?: {
    id: string;
    name: string;
    nodeType: string;
  };
}

export interface CallChainNode {
  depth: number;
  nodeId: string;
  nodeName: string;
  nodeType: string;
  callName: string;
  callType: "static" | "dynamic" | "unknown";
  path: string[];
}

export async function getCallEdges(params: {
  file_id?: string;
  repository_id?: string;
}): Promise<CallEdge[]> {
  const searchParams = new URLSearchParams();
  if (params.file_id) searchParams.set("file_id", params.file_id);
  if (params.repository_id) searchParams.set("repository_id", params.repository_id);
  const query = searchParams.toString();
  return apiFetch(`/api/v1/call-edges${query ? `?${query}` : ""}`);
}

export async function getCallees(nodeId: string): Promise<CallEdgeWithNode[]> {
  return apiFetch(`/api/v1/call-edges/${nodeId}/callees`);
}

export async function getCallers(nodeId: string): Promise<CallEdgeWithNode[]> {
  return apiFetch(`/api/v1/call-edges/${nodeId}/callers`);
}

export async function getCallChain(nodeId: string, maxDepth: number = 10): Promise<CallChainNode[]> {
  return apiFetch(`/api/v1/call-edges/${nodeId}/chain?max_depth=${maxDepth}`);
}
