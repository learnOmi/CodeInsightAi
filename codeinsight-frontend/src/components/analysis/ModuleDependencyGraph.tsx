"use client";

import { useMemo, useState, useCallback, useRef, useEffect } from "react";
import { useModuleDependencies } from "@/hooks/use-analysis-results";
import { useFiles, type FileItem } from "@/hooks/use-files";
import "@xyflow/react/dist/style.css";
import type { NavigableProps } from "@/components/analysis/NavTrailBar";
import { Handle, Position, ReactFlow, Background, type Node, type Edge, type NodeTypes } from "@xyflow/react";

// ─── Props ───────────────────────────────────────
interface ModuleDependencyGraphProps extends NavigableProps {
  repositoryId: string;
}

interface NodeItem {
  id: string;
  name: string;
  type: "file" | "internal" | "external";
  fullPath?: string;
}

interface ExploreNodeData {
  label: string;
  nodeType: "file" | "internal" | "external";
  fullPath?: string;
  nodeId?: string;
  resolvable?: boolean;
  onNavigate?: (entry: { component?: string; fileId?: string; label: string; detail?: string }) => void;
}

const NODE_W = 160;
const NODE_H = 44;

function isInternalImport(importName: string): boolean {
  return ["./", "../", "@/", "~/"].some((p) => importName.startsWith(p));
}

function shortPath(filePath: string, maxLen = 28): string {
  if (!filePath) return "";
  if (filePath.length <= maxLen) return filePath;
  const parts = filePath.replace(/\\/g, "/").split("/");
  let result = parts[parts.length - 1];
  for (let i = parts.length - 2; i >= 0; i--) {
    const candidate = `${parts[i]}/${result}`;
    if (candidate.length > maxLen) break;
    result = candidate;
  }
  return `…/${result}`;
}

function truncate(text: string, maxLen: number): string {
  if (!text) return "";
  return text.length > maxLen ? text.slice(0, maxLen - 1) + "…" : text;
}

function ExploreNode({ data }: { data: ExploreNodeData }) {
  const colorMap = {
    file: { bg: "rgba(75, 85, 99, 0.35)", border: "rgba(107, 114, 128, 0.8)", accent: "#6b7280", label: "文件" },
    internal: { bg: "rgba(20, 184, 166, 0.25)", border: "rgba(20, 184, 166, 0.8)", accent: "#14b8a6", label: "内部模块" },
    external: { bg: "rgba(168, 85, 247, 0.25)", border: "rgba(168, 85, 247, 0.8)", accent: "#a855f7", label: "外部依赖" },
  };
  const c = colorMap[data.nodeType];

  return (
    <div
      className="px-3 py-2 flex flex-col items-center justify-center cursor-pointer select-none transition-all hover:brightness-125"
      style={{
        backgroundColor: c.bg,
        border: `2px solid ${c.border}`,
        borderRadius: 10,
        width: NODE_W,
        color: "var(--text-primary)",
      }}
      title={`${data.label}\n${data.fullPath || ""}\n类型: ${c.label}`}
    >
      <Handle type="source" position={Position.Right} id="source" style={{ background: c.accent }} />
      <Handle type="target" position={Position.Left} id="target" style={{ background: c.accent }} />
      <div className="flex items-center gap-1.5 w-full justify-center">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: c.accent }} />
        <span className="font-semibold text-xs truncate" style={{ color: "var(--text-primary)" }}>
          {truncate(data.label, 22)}
        </span>
      </div>
      <div className="text-[10px] mt-0.5 opacity-60" style={{ color: "var(--text-muted)" }}>
        {c.label}
      </div>
      {data.onNavigate && (
        <div className="flex gap-1 mt-1.5">
          {data.resolvable === false ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-500/20 text-gray-400" title="无法解析到具体文件">
              无法解析
            </span>
          ) : (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  data.onNavigate!({ component: "callgraph", fileId: data.nodeId, label: data.label, detail: "调用图" });
                }}
                className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors"
                title="查看调用图"
              >
                ⊙调用图
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  data.onNavigate!({ component: "structure", fileId: data.nodeId, label: data.label, detail: "代码结构" });
                }}
                className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
                title="查看代码结构"
              >
                ◆结构
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const nodeTypes: NodeTypes = { exploreNode: ExploreNode };

export function ModuleDependencyGraph({ repositoryId, onNavigate }: ModuleDependencyGraphProps) {
  const { data: deps, isLoading, error } = useModuleDependencies(repositoryId);
  const { data: files } = useFiles(repositoryId);

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [history, setHistory] = useState<string[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);

  const fileIdMap = useMemo(() => {
    const map = new Map<string, FileItem>();
    files?.forEach((f) => map.set(f.id, f));
    return map;
  }, [files]);

  const filePathToIdMap = useMemo(() => {
    const map = new Map<string, string>();
    files?.forEach((f) => map.set(f.path, f.id));
    return map;
  }, [files]);

  const fileSuffixToIdMap = useMemo(() => {
    const map = new Map<string, string>();
    files?.forEach((f) => {
      const normalized = f.path.replace(/\\/g, "/");
      map.set(normalized, f.id);
      const segments = normalized.split("/");
      for (let i = 1; i < segments.length; i++) {
        const suffix = segments.slice(i).join("/");
        if (!map.has(suffix)) {
          map.set(suffix, f.id);
        }
      }
    });
    return map;
  }, [files]);

  const resolveInternalPath = useCallback((importPath: string): string | undefined => {
    let relPath = importPath;
    const aliasPrefixes = ["@/", "~/", "@app/", "@src/"];
    for (const prefix of aliasPrefixes) {
      if (relPath.startsWith(prefix)) {
        relPath = relPath.slice(prefix.length);
        break;
      }
    }
    if (relPath.startsWith("./") || relPath.startsWith("../")) {
      relPath = relPath.replace(/^\.\//, "").replace(/^\.\.\//, "");
    }
    const exts = [".ts", ".tsx", ".vue", ".js", ".jsx", ".mjs", ".cjs",
                  "/index.ts", "/index.tsx", "/index.vue", "/index.js", "/index.jsx"];
    const hasExt = exts.some(ext => relPath.endsWith(ext));
    const candidates: string[] = [];
    if (hasExt) {
      candidates.push(relPath);
    } else {
      for (const ext of exts) {
        candidates.push(relPath + ext);
      }
    }
    for (const candidate of candidates) {
      if (filePathToIdMap.has(candidate)) {
        return filePathToIdMap.get(candidate);
      }
    }
    for (const candidate of candidates) {
      if (fileSuffixToIdMap.has(candidate)) {
        return fileSuffixToIdMap.get(candidate);
      }
      const srcCandidate = "src/" + candidate;
      if (fileSuffixToIdMap.has(srcCandidate)) {
        return fileSuffixToIdMap.get(srcCandidate);
      }
    }
    console.warn("[ModuleDependencyGraph] 无法解析内部路径:", importPath, "已尝试候选:", candidates, "文件路径样本:", Array.from(filePathToIdMap.keys()).slice(0, 5));
    return undefined;
  }, [filePathToIdMap, fileSuffixToIdMap]);

  const { nodeMap, allNodes, hotNodes, stats } = useMemo(() => {
    if (!deps || !Array.isArray(deps) || deps.length === 0) {
      return { nodeMap: new Map(), allNodes: [], hotNodes: [], stats: null };
    }

    const map = new Map<string, NodeItem>();
    const refCount = new Map<string, number>();

    for (const dep of deps) {
      const importerFile = fileIdMap.get(dep.importerFileId);
      const importerPath = importerFile?.path || dep.importerFileId;

      if (!map.has(dep.importerFileId)) {
        map.set(dep.importerFileId, {
          id: dep.importerFileId,
          name: importerPath.split(/[/\\]/).pop() || dep.importerFileId,
          type: "file",
          fullPath: importerPath,
        });
      }

      const isInternal = isInternalImport(dep.importName);
      const modType: "internal" | "external" = isInternal ? "internal" : "external";

      if (!map.has(dep.importName)) {
        map.set(dep.importName, {
          id: dep.importName,
          name: dep.importName,
          type: modType,
        });
      }

      refCount.set(dep.importName, (refCount.get(dep.importName) || 0) + 1);
    }

    const allNodes = Array.from(map.values());
    const hotNodes = Array.from(map.entries())
      .map(([id, item]) => ({ ...item, refCount: refCount.get(id) || 0 }))
      .sort((a, b) => b.refCount - a.refCount)
      .slice(0, 10);

    const statsData = {
      totalDeps: deps.length,
      totalNodes: map.size,
      fileNodes: allNodes.filter((n) => n.type === "file").length,
      internalNodes: allNodes.filter((n) => n.type === "internal").length,
      externalNodes: allNodes.filter((n) => n.type === "external").length,
    };

    return { nodeMap: map, allNodes, hotNodes, stats: statsData };
  }, [deps, fileIdMap]);

  const forwardEdges = useMemo(() => {
    const map = new Map<string, Set<string>>();
    if (!deps || !Array.isArray(deps)) return map;

    for (const dep of deps) {
      if (!map.has(dep.importerFileId)) map.set(dep.importerFileId, new Set());
      map.get(dep.importerFileId)!.add(dep.importName);
    }
    return map;
  }, [deps]);

  const reverseEdges = useMemo(() => {
    const map = new Map<string, Set<string>>();
    if (!deps || !Array.isArray(deps)) return map;

    for (const dep of deps) {
      if (!map.has(dep.importName)) map.set(dep.importName, new Set());
      map.get(dep.importName)!.add(dep.importerFileId);
    }
    return map;
  }, [deps]);

  const filteredNodes = useMemo(() => {
    if (!searchQuery) return allNodes;
    const q = searchQuery.toLowerCase();
    return allNodes.filter((n) => n.name.toLowerCase().includes(q) || (n.fullPath && n.fullPath.toLowerCase().includes(q)));
  }, [searchQuery, allNodes]);

  const { nodes, edges } = useMemo(() => {
    if (!selectedNodeId) return { nodes: [], edges: [] };

    const centerNode = nodeMap.get(selectedNodeId);
    if (!centerNode) return { nodes: [], edges: [] };

    const importTargets = forwardEdges.get(selectedNodeId) || new Set();
    const importedBy = reverseEdges.get(selectedNodeId) || new Set();

    const rfNodes: Node[] = [];
    const rfEdges: Edge[] = [];

    let centerNavNodeId = selectedNodeId;
    let centerResolvable = true;
    if (centerNode.type === "internal") {
      const resolved = resolveInternalPath(selectedNodeId);
      if (resolved) {
        centerNavNodeId = resolved;
      } else {
        centerResolvable = false;
      }
    }

    rfNodes.push({
      id: selectedNodeId,
      type: "exploreNode",
      position: { x: 400, y: 280 },
      width: NODE_W,
      height: NODE_H,
      data: {
        label: centerNode.name,
        nodeType: centerNode.type,
        fullPath: centerNode.fullPath,
        nodeId: centerNavNodeId,
        resolvable: centerResolvable,
        onNavigate,
      } as unknown as Record<string, unknown>,
    });

    const neighbors = new Map<string, { type: "imports" | "importedBy"; name: string; nodeType: "file" | "internal" | "external"; fullPath?: string }>();

    for (const target of importTargets) {
      const targetNode = nodeMap.get(target);
      if (targetNode) {
        neighbors.set(target, { type: "imports", name: targetNode.name, nodeType: targetNode.type, fullPath: targetNode.fullPath });
      }
    }

    for (const importerId of importedBy) {
      const importerNode = nodeMap.get(importerId);
      if (importerNode) {
        neighbors.set(importerId, { type: "importedBy", name: importerNode.name, nodeType: importerNode.type, fullPath: importerNode.fullPath });
      }
    }

    const neighborList = Array.from(neighbors.entries());
    const importNeighbors = neighborList.filter(([, info]) => info.type === "imports");
    const importedByNeighbors = neighborList.filter(([, info]) => info.type === "importedBy");

    const layoutNode = (neighborId: string, info: typeof neighborList[0][1], x: number, y: number) => {
      let navNodeId = neighborId;
      let resolvable = true;
      if (info.nodeType === "internal") {
        const resolved = resolveInternalPath(neighborId);
        if (resolved) {
          navNodeId = resolved;
        } else {
          resolvable = false;
        }
      } else if (info.nodeType === "external") {
        resolvable = false;
      }
      rfNodes.push({
        id: neighborId,
        type: "exploreNode",
        position: { x, y },
        width: NODE_W,
        height: NODE_H,
        data: {
          label: info.name,
          nodeType: info.nodeType,
          fullPath: info.fullPath,
          nodeId: navNodeId,
          resolvable,
          onNavigate,
        } as unknown as Record<string, unknown>,
      });

      const edgeDir = info.type === "imports" ? { source: selectedNodeId, target: neighborId } : { source: neighborId, target: selectedNodeId };
      rfEdges.push({
        id: `edge-${selectedNodeId}-${neighborId}`,
        source: edgeDir.source,
        sourceHandle: "source",
        target: edgeDir.target,
        targetHandle: "target",
        style: {
          stroke: info.type === "imports" ? "#60a5fa" : "#f87171",
          strokeWidth: 3,
        },
      });
    };

    const maxPerSide = Math.max(importNeighbors.length, importedByNeighbors.length);
    const verticalGap = Math.max(85, 400 / maxPerSide);
    const startY = 280 - ((maxPerSide - 1) * verticalGap) / 2;

    importNeighbors.forEach(([neighborId, info], i) => {
      layoutNode(neighborId, info, 620, startY + i * verticalGap);
    });

    importedByNeighbors.forEach(([neighborId, info], i) => {
      layoutNode(neighborId, info, 180, startY + i * verticalGap);
    });

    return { nodes: rfNodes, edges: rfEdges };
  }, [selectedNodeId, nodeMap, forwardEdges, reverseEdges, onNavigate, resolveInternalPath]);

  const handleSelectNode = useCallback((nodeId: string) => {
    if (selectedNodeId) {
      setHistory((prev) => [...prev, selectedNodeId]);
    }
    setSelectedNodeId(nodeId);
    setSearchQuery("");
    if (inputRef.current) inputRef.current.blur();
  }, [selectedNodeId]);

  const handleBack = useCallback(() => {
    if (history.length > 0) {
      const prevId = history[history.length - 1];
      setHistory((prev) => prev.slice(0, -1));
      setSelectedNodeId(prevId);
    }
  }, [history]);

  const handleClear = useCallback(() => {
    setSelectedNodeId(null);
    setHistory([]);
    setSearchQuery("");
  }, []);

  useEffect(() => {
    if (selectedNodeId) {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") handleClear();
        if (e.key === "ArrowLeft" && e.ctrlKey) handleBack();
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [selectedNodeId, handleClear, handleBack]);

  if (isLoading) {
    return (
      <div className="h-[600px] flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-[var(--text-muted)]">加载模块依赖数据...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-[600px] flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-red-500">加载模块依赖数据失败</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">{error.message}</p>
        </div>
      </div>
    );
  }

  if (!stats || stats.totalDeps === 0) {
    return (
      <div className="h-[600px] flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-[var(--text-muted)]">暂无模块依赖数据</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-[var(--text-primary)]">模块依赖探索</h3>
        {stats && (
          <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
            <span>{stats.totalDeps} 依赖关系</span>
            <span>·</span>
            <span>{stats.fileNodes} 源文件</span>
            <span>·</span>
            <span>{stats.internalNodes} 内部模块</span>
            <span>·</span>
            <span>{stats.externalNodes} 外部依赖</span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <input
            ref={inputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索文件或模块名称..."
            className="w-full px-4 py-2 text-sm bg-[var(--bg-card)] border border-[var(--border)] rounded-lg text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        {selectedNodeId && (
          <>
            <button
              onClick={handleBack}
              disabled={history.length === 0}
              className="px-3 py-2 text-sm bg-[var(--bg-card)] border border-[var(--border)] rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--text-muted)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="后退 (Ctrl+←)"
            >
              ← 返回
            </button>
            <button
              onClick={handleClear}
              className="px-3 py-2 text-sm bg-[var(--bg-card)] border border-[var(--border)] rounded-lg text-[var(--text-muted)] hover:text-red-500 hover:border-red-500 transition-colors"
              title="重置 (Esc)"
            >
              重置
            </button>
          </>
        )}
      </div>

      {searchQuery && filteredNodes.length > 0 && (
        <div className="max-h-[200px] overflow-y-auto bg-[var(--bg-card)] border border-[var(--border)] rounded-lg">
          {filteredNodes.map((node) => (
            <button
              key={node.id}
              onClick={() => handleSelectNode(node.id)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-hover)] transition-colors text-left border-b border-[var(--border)] last:border-b-0"
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{
                  backgroundColor:
                    node.type === "file" ? "#6b7280" : node.type === "internal" ? "#14b8a6" : "#a855f7",
                }}
              />
              <span className="text-sm text-[var(--text-primary)] truncate">{node.name}</span>
              {node.fullPath && (
                <span className="text-xs text-[var(--text-muted)] truncate ml-auto">{shortPath(node.fullPath)}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {!selectedNodeId && !searchQuery && (
        <div className="mb-3">
          <p className="text-xs text-[var(--text-muted)] mb-2">热门节点（引用次数最多）：</p>
          <div className="flex flex-wrap gap-2">
            {hotNodes.map((node) => (
              <button
                key={node.id}
                onClick={() => handleSelectNode(node.id)}
                className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
                  node.type === "file"
                    ? "border-gray-400 hover:bg-gray-500 hover:text-white text-gray-600"
                    : node.type === "internal"
                    ? "border-teal-400 hover:bg-teal-500 hover:text-white text-teal-600"
                    : "border-purple-400 hover:bg-purple-500 hover:text-white text-purple-600"
                }`}
                title={`${node.name}\n引用 ${node.refCount} 次`}
              >
                {truncate(node.name, 20)} ×{node.refCount}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="h-[calc(100vh-450px)] min-h-[600px] bg-[var(--bg-card)] rounded-lg border border-[var(--border)] overflow-hidden relative">
        {selectedNodeId ? (
          <>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodeClick={(_, node) => handleSelectNode(node.id)}
              fitView
              fitViewOptions={{ padding: 0.2, duration: 500 }}
              minZoom={0.5}
              maxZoom={2}
              defaultEdgeOptions={{ type: "smoothstep" }}
            >
              <Background color="#374151" gap={16} />
            </ReactFlow>
            <div className="absolute bottom-4 left-4 bg-black/70 text-white px-3 py-2 rounded text-xs z-10">
              节点: {nodes.length} | 边: {edges.length}
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-500/10 flex items-center justify-center">
                <span className="text-3xl">🔍</span>
              </div>
              <h4 className="text-lg font-medium text-[var(--text-primary)] mb-2">探索模块依赖关系</h4>
              <p className="text-sm text-[var(--text-muted)]">
                在上方搜索框输入文件名或模块名，选择一个起始节点开始探索其依赖网络。点击图中的任意节点可继续探索。
              </p>
              <div className="mt-4 flex items-center justify-center gap-4 text-xs text-[var(--text-muted)]">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded border border-gray-400 bg-gray-500" /> 文件
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded border border-teal-400 bg-teal-500" /> 内部模块
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded border border-purple-400 bg-purple-500" /> 外部依赖
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {selectedNodeId && (
        <div className="flex flex-wrap gap-4 text-xs text-[var(--text-muted)]">
          <span className="flex items-center gap-1">
            <span className="text-blue-400">→ imports</span> 当前节点导入的模块
          </span>
          <span className="flex items-center gap-1">
            <span className="text-red-400">← imported by</span> 导入当前节点的文件
          </span>
          <span className="flex items-center gap-1">
            <span className="text-[var(--text-muted)]">点击节点</span> 继续探索
          </span>
          <span className="flex items-center gap-1">
            <span className="text-[var(--text-muted)]">Esc</span> 重置
          </span>
        </div>
      )}
    </div>
  );
}
