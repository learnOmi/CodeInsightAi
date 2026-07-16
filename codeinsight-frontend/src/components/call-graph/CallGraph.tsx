/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import React, { useCallback, useMemo, useState, useEffect } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import Elk from "elkjs";
import { useAstNodes, useCallEdges } from "@/hooks/use-files";
import { CallChainPanel } from "./CallChainPanel";
import "@xyflow/react/dist/style.css";

const ELKConstructor = Elk;

interface CallGraphProps {
  fileId: string;
  repositoryId: string;
}

// 节点类型配色
const NODE_TYPE_CONFIG: Record<string, { color: string; borderColor: string; label: string; icon: string }> = {
  function: { color: "#3b82f6", borderColor: "#1d4ed8", label: "函数", icon: "λ" },
  method: { color: "#8b5cf6", borderColor: "#6d28d9", label: "方法", icon: "·" },
  constructor: { color: "#f59e0b", borderColor: "#d97706", label: "构造器", icon: "⚙" },
  class: { color: "#ec4899", borderColor: "#db2777", label: "类", icon: "C" },
  interface: { color: "#14b8a6", borderColor: "#0d9488", label: "接口", icon: "I" },
  enum: { color: "#f97316", borderColor: "#ea580c", label: "枚举", icon: "E" },
  struct: { color: "#84cc16", borderColor: "#65a30d", label: "结构体", icon: "S" },
  call: { color: "#9ca3af", borderColor: "#6b7280", label: "调用", icon: "→" },
};

const NODE_W = 160;
const NODE_H = 64;

const CALL_TYPE_STYLES: Record<string, { stroke: string; strokeDasharray: string; width: number }> = {
  static: { stroke: "#60a5fa", strokeDasharray: "0", width: 2 },
  dynamic: { stroke: "#fbbf24", strokeDasharray: "5,5", width: 2 },
  unknown: { stroke: "#9ca3af", strokeDasharray: "2,3", width: 1 },
};

const CLASS_TYPES = new Set(["class"]);
const MEMBER_TYPES = new Set(["function", "method", "constructor"]);
const MAX_HANDLES = 6;

const elk = new ELKConstructor({
  defaultLayoutOptions: {
    "elk.algorithms.layered": "true",
    "elk.layered.spacing.nodeNodeBetweenLayers": "140",
    "elk.layered.spacing.nodeNodeWithinLayers": "100",
    "elk.direction": "DOWN",
    "elk.unflatten": "true",
    "elk.layered.unflatten.maxDegree": "1",
    "elk.layered.considerModelOrder": "true",
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  },
});

// 节点 tooltip 描述生成
function buildNodeTooltip(data: any): string {
  const lines = [`${data.nodeTypeLabel}：${data.label}`];
  if (!data.isCurrentFile && data.filePath) {
    lines.push(`文件：${data.filePath}`);
  }
  if (data.callsMade > 0) lines.push(`调用 ${data.callsMade} 个方法`);
  if (data.callsReceived > 0) lines.push(`被 ${data.callsReceived} 个方法调用`);
  return lines.join(" | ");
}

/**
 * 截断文件路径为简短格式
 * 例如: "src/api/clazz.js" → "…api/clazz.js"
 */
function shortFilePath(filePath: string, maxLen = 24): string {
  if (!filePath || filePath.length <= maxLen) return filePath || "";
  const parts = filePath.split(/[/\\]/);
  let result = parts[parts.length - 1];
  for (let i = parts.length - 2; i >= 0; i--) {
    const candidate = `${parts[i]}/${result}`;
    if (candidate.length > maxLen) break;
    result = candidate;
  }
  return `…${result.startsWith("/") || result.startsWith("\\") ? "" : "/"}${result}`;
}

/**
 * 自定义 CallGraph 节点 — 渲染多个 Handle + tooltip
 */
function CallGraphNode({ data, isClass, isMember }: any) {
  const [hovered, setHovered] = useState(false);

  // 调用点节点：极简样式，只作为边连接点
  if (data.isCallSite) {
    return (
      <div
        className="relative flex items-center justify-center cursor-pointer select-none"
        style={{
          width: 80,
          height: 28,
          backgroundColor: "rgba(107, 114, 128, 0.08)",
          border: "1px dashed rgba(107, 114, 128, 0.3)",
          borderRadius: 4,
          fontSize: 10,
          color: "rgba(255, 255, 255, 0.5)",
          fontWeight: 400,
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <span className="truncate px-1">{data.label}</span>
        {hovered && (
          <div
            className="absolute z-50 bottom-full left-1/2 mb-2 px-2 py-1 text-xs whitespace-nowrap rounded shadow-lg pointer-events-none"
            style={{ transform: "translateX(-50%)", backgroundColor: "#1f2937", color: "#e5e7eb" }}
          >
            {buildNodeTooltip(data)}
          </div>
        )}
        <Handle
          id="source-0"
          type="source"
          position={Position.Bottom}
          style={{ background: "rgba(107, 114, 128, 0.5)", width: 6, height: 6 }}
        />
        <Handle
          id="target-0"
          type="target"
          position={Position.Top}
          style={{ background: "rgba(107, 114, 128, 0.5)", width: 6, height: 6 }}
        />
      </div>
    );
  }

  return (
    <div
      className="relative px-3 py-2 text-center font-medium cursor-pointer"
      style={{
        backgroundColor: data.isCurrentFile
          ? (isClass ? "rgba(236, 72, 153, 0.15)" : data.color)
          : "rgba(107, 114, 128, 0.25)",
        borderColor: data.isCurrentFile ? data.borderColor : "#6b7280",
        borderWidth: isClass ? 2 : isMember ? 2.5 : 2,
        borderStyle: data.isCurrentFile ? "solid" : "dashed",
        borderRadius: 8,
        color: "#ffffff",
        fontSize: data.label.length > 14 ? 12 : 14,
        fontWeight: isClass ? 700 : 600,
        letterSpacing: data.label.length > 14 ? -0.5 : 0,
        opacity: data.isCurrentFile ? 1 : 0.85,
        height: NODE_H,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 0,
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="flex items-center gap-1" style={{ marginTop: data.isCurrentFile ? 0 : -4 }}>
        <span className="text-xs opacity-75">{data.icon}</span>
        <span className="truncate">{data.label}</span>
      </div>
      {/* 非当前文件节点：显示文件路径小标签 */}
      {!data.isCurrentFile && data.filePath && (
        <div
          className="text-[10px] leading-tight truncate max-w-full"
          style={{ opacity: 0.6, marginTop: 1 }}
        >
          {shortFilePath(data.filePath)}
        </div>
      )}
      {/* tooltip */}
      {hovered && (
        <div
          className="absolute z-50 bottom-full left-1/2 mb-2 px-2 py-1 text-xs whitespace-nowrap rounded shadow-lg pointer-events-none"
          style={{ transform: "translateX(-50%)", backgroundColor: "#1f2937", color: "#e5e7eb" }}
        >
          {buildNodeTooltip(data)}
        </div>
      )}
      {Array.from({ length: MAX_HANDLES }, (_, i) => (
        <Handle
          key={`source-${i}`}
          id={`source-${i}`}
          type="source"
          position={Position.Bottom}
          style={{
            background: data.borderColor,
            left: `${(i + 0.5) / (MAX_HANDLES + 1) * 100}%`,
            width: 8,
            height: 8,
          }}
        />
      ))}
      {Array.from({ length: MAX_HANDLES }, (_, i) => (
        <Handle
          key={`target-${i}`}
          id={`target-${i}`}
          type="target"
          position={Position.Top}
          style={{
            background: data.borderColor,
            left: `${(i + 0.5) / (MAX_HANDLES + 1) * 100}%`,
            width: 8,
            height: 8,
          }}
        />
      ))}
    </div>
  );
}

const nodeTypes = { callNode: CallGraphNode };

/**
 * 构建 React Flow 图数据
 * 只显示当前文件节点 + 被调用到的外部节点
 * 按 (caller, callee) 合并重复边（同名调用只画一条）
 */
async function buildGraphData(
  astNodes: any[],
  callEdges: any[],
  currentFileId?: string,
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  if (!astNodes.length || !callEdges.length) {
    return { nodes: [], edges: [] };
  }

  const callableTypes = new Set(["function", "method", "constructor", "class", "interface", "enum", "struct"]);
  const callableNodes = astNodes.filter((n: any) => callableTypes.has(n.nodeType));

  const nodeMap = new Map<string, any>();
  callableNodes.forEach((n: any) => nodeMap.set(n.id, n));

  // 扩展 nodeMap：当前文件的 call 节点也加入，模块级匿名回调内调用可保留边
  const currentFileCallNodes = currentFileId
    ? astNodes.filter((n: any) => n.nodeType === "call" && n.fileId === currentFileId)
    : [];
  currentFileCallNodes.forEach((n: any) => nodeMap.set(n.id, n));

  // 只保留两端的节点都在 nodeMap 中的边
  const validEdges = callEdges.filter((e: any) => e.calleeNodeId && nodeMap.has(e.callerNodeId) && nodeMap.has(e.calleeNodeId));

  if (validEdges.length === 0) {
    return { nodes: [], edges: [] };
  }

  // === 按 (caller, callee) 合并重复边 ===
  // 后端为每个 call_expression 生成一条独立边，
  // 前端需要合并为唯一的 (caller→callee) 对，避免重复节点和重叠边
  const uniqueEdgeMap = new Map<string, { count: number; edge: any }>();
  for (const edge of validEdges) {
    const key = `${edge.callerNodeId}→${edge.calleeNodeId}`;
    const existing = uniqueEdgeMap.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      uniqueEdgeMap.set(key, { count: 1, edge });
    }
  }

  // 展开为唯一边列表，每条边附带调用次数
  const uniqueEdges = Array.from(uniqueEdgeMap.values()).map(({ count, edge }) => ({ ...edge, callCount: count }));

  // 统计唯一 callee 的出度/入度（用于 tooltip）
  const outDegree = new Map<string, number>();
  const inDegree = new Map<string, number>();
  for (const edge of uniqueEdges) {
    outDegree.set(edge.callerNodeId, (outDegree.get(edge.callerNodeId) || 0) + 1);
    inDegree.set(edge.calleeNodeId, (inDegree.get(edge.calleeNodeId) || 0) + 1);
  }

  // 统计原始调用次数（同一 callee 被调用多少次）
  const callSiteCount = new Map<string, number>();
  for (const edge of validEdges) {
    const key = `${edge.callerNodeId}→${edge.calleeNodeId}`;
    callSiteCount.set(key, (callSiteCount.get(key) || 0) + 1);
  }

  // 只收集边涉及的节点
  const involvedNodeIds = new Set<string>();
  for (const edge of uniqueEdges) {
    involvedNodeIds.add(edge.callerNodeId);
    involvedNodeIds.add(edge.calleeNodeId);
  }

  // 统计每个源节点的出边数（handle 分配用）
  const outEdgesPerNode = new Map<string, number>();
  for (const edge of uniqueEdges) {
    outEdgesPerNode.set(edge.callerNodeId, (outEdgesPerNode.get(edge.callerNodeId) || 0) + 1);
  }

  // 构建 ELK 输入
  const elkNodes: Array<{ id: string; width: number; height: number; label?: string }> = [];
  const elkEdges: Array<{ id: string; sources: string[]; targets: string[]; label?: string }> = [];

  for (const nodeId of involvedNodeIds) {
    const node = nodeMap.get(nodeId);
    if (!node) continue;
    elkNodes.push({ id: node.id, width: NODE_W, height: NODE_H, label: node.name });
  }

  // ELK 布局只使用唯一边，避免重复节点
  for (const edge of uniqueEdges) {
    elkEdges.push({ id: edge.id, sources: [edge.callerNodeId], targets: [edge.calleeNodeId], label: edge.callName });
  }

  const layoutGraph = await elk.layout({
    id: "root", label: "call-graph", layoutOptions: {},
    children: elkNodes, edges: elkEdges,
  });

  // 转换为 React Flow 节点
  const children = layoutGraph.children || [];
  const graphNodes: Node[] = [];

  for (const child of children) {
    const nodeId = child.id as string;
    const astNode = nodeMap.get(nodeId);
    if (!astNode) continue;

    const isCallNode = astNode.nodeType === "call";

    if (isCallNode) {
      // 当前文件 call 节点：渲染为极小节点，只作为边连接点
      graphNodes.push({
        id: nodeId,
        type: "callNode",
        position: { x: Number(child.x) || 0, y: Number(child.y) || 0 },
        width: 80,
        height: 28,
        data: {
          label: astNode.name,
          nodeType: "call",
          nodeTypeLabel: "调用点",
          icon: "▸",
          color: "rgba(107, 114, 128, 0.12)",
          borderColor: "rgba(107, 114, 128, 0.35)",
          isClass: false,
          isMember: false,
          isCurrentFile: true,
          filePath: astNode.filePath,
          callsMade: outDegree.get(nodeId) || 0,
          callsReceived: inDegree.get(nodeId) || 0,
          isCallSite: true,
        },
      });
      continue;
    }

    const config = NODE_TYPE_CONFIG[astNode.nodeType] || NODE_TYPE_CONFIG.function;
    const isClass = CLASS_TYPES.has(astNode.nodeType);
    const isMember = MEMBER_TYPES.has(astNode.nodeType);

    graphNodes.push({
      id: nodeId,
      type: "callNode",
      position: { x: Number(child.x) || 0, y: Number(child.y) || 0 },
      width: NODE_W,
      height: NODE_H,
      data: {
        label: astNode.name,
        nodeType: astNode.nodeType,
        nodeTypeLabel: config.label,
        icon: config.icon,
        color: config.color,
        borderColor: config.borderColor,
        isClass,
        isMember,
        isCurrentFile: astNode.fileId === currentFileId,
        filePath: astNode.filePath,
        callsMade: outDegree.get(nodeId) || 0,
        callsReceived: inDegree.get(nodeId) || 0,
      },
    });
  }

  // 构建边 — 默认隐藏标签，使用唯一边
  const graphEdges: Edge[] = [];
  const outEdgeCounter = new Map<string, number>();

  for (const edge of uniqueEdges) {
    const style = CALL_TYPE_STYLES[edge.callType] || CALL_TYPE_STYLES.unknown;
    const counter = outEdgeCounter.get(edge.callerNodeId) || 0;
    outEdgeCounter.set(edge.callerNodeId, counter + 1);

    const sourceHandle = counter < MAX_HANDLES ? `source-${counter}` : undefined;
    const targetHandle = counter < MAX_HANDLES ? `target-${counter}` : undefined;

    graphEdges.push({
      id: edge.id,
      source: edge.callerNodeId,
      target: edge.calleeNodeId,
      sourceHandle,
      targetHandle,
      type: "smoothstep",
      animated: edge.callType === "dynamic",
      style: {
        stroke: style.stroke,
        strokeDasharray: style.strokeDasharray,
        strokeWidth: style.width,
      },
      // 默认隐藏标签，通过 data.label 存储，edge hover 时再显示
      label: undefined,
      labelStyle: { opacity: 0 },
      labelBgStyle: { opacity: 0 },
      data: { callName: edge.callName, callCount: edge.callCount },
      markerEnd: { type: "arrowclosed", width: 10, height: 10, color: style.stroke },
    });
  }

  return { nodes: graphNodes, edges: graphEdges };
}

/** 图例下拉按钮 */
function LegendDropdown({ edgeCounts }: { edgeCounts: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors px-2 py-1 rounded hover:bg-gray-100"
      >
        <span>图例</span>
        <span className="text-[9px]">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-50 bg-white rounded-lg shadow-xl border border-gray-200 p-4 min-w-[280px]">
            <div className="space-y-3">
              {/* 节点类型 */}
              <div>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">节点类型</p>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                  {Object.entries(NODE_TYPE_CONFIG).map(([type, config]) => (
                    <span key={type} className="flex items-center gap-1.5 text-[11px] text-gray-500">
                      <span className="w-2.5 h-2.5 rounded flex-shrink-0" style={{ backgroundColor: config.color }} />
                      <span>{config.label}</span>
                    </span>
                  ))}
                </div>
              </div>
              {/* 调用类型 */}
              <div>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">调用类型</p>
                <div className="space-y-1">
                  {["static", "dynamic", "unknown"].map((type) => (
                    <span key={type} className="flex items-center gap-1.5 text-[11px] text-gray-500">
                      <span className="w-6 h-0.5 flex-shrink-0" style={{
                        backgroundColor: CALL_TYPE_STYLES[type].stroke,
                        ...(CALL_TYPE_STYLES[type].strokeDasharray ? { borderTop: `1px dashed ${CALL_TYPE_STYLES[type].stroke}`, backgroundColor: "transparent" } : {}),
                      }} />
                      <span>{type} ({edgeCounts[type] || 0})</span>
                    </span>
                  ))}
                </div>
              </div>
              {/* 特殊样式 */}
              <div>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">特殊样式</p>
                <div className="space-y-1">
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-500">
                    <span className="w-2.5 h-2.5 rounded border border-dashed flex-shrink-0" style={{ borderColor: "#6b7280", backgroundColor: "rgba(107,114,128,0.3)" }} />
                    <span>跨文件节点（灰色虚线）</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-500">
                    <span className="inline-block text-[9px] leading-none px-1 rounded flex-shrink-0" style={{ border: "1px dashed rgba(107,114,128,0.3)", color: "rgba(255,255,255,0.5)", backgroundColor: "rgba(107,114,128,0.08)" }}>
                      ▸
                    </span>
                    <span>调用点（模块级匿名回调内调用）</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function CallGraph({ fileId, repositoryId }: CallGraphProps) {
  // 用 file_id 查调用边（仅当前文件的调用）
  const { data: callEdges, isLoading: edgesLoading } = useCallEdges({ file_id: fileId });
  // 用 repository_id 查所有 AST 节点，后续在前端过滤
  const { data: allAstNodes, isLoading: astLoading } = useAstNodes({ repository_id: repositoryId });

  const isLoading = astLoading || edgesLoading;
  const [graphData, setGraphData] = useState<{ nodes: Node[]; edges: Edge[] } | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [selectedNodeForChain, setSelectedNodeForChain] = useState<string | null>(null);

  // 获取选中调用链节点的详细信息
  const chainNodeData = useMemo(() => {
    if (!selectedNodeForChain || !graphData) return null;
    const node = graphData.nodes.find((n) => n.id === selectedNodeForChain);
    if (!node) return null;
    const d = node.data as any;
    return { id: selectedNodeForChain, name: d.label, nodeType: d.nodeType, filePath: d.filePath };
  }, [selectedNodeForChain, graphData]);

  useEffect(() => {
    if (!allAstNodes || !callEdges) {
      setGraphData(null);
      setFocusedNodeId(null);
      setHoveredEdgeId(null);
      return;
    }
    // 从调用边中提取所有涉及的节点 ID
    const involvedNodeIds = new Set<string>();
    for (const edge of callEdges) {
      involvedNodeIds.add(edge.callerNodeId);
      if (edge.calleeNodeId) involvedNodeIds.add(edge.calleeNodeId);
    }
    // 只保留涉及到的 AST 节点，并按 (file_id, start_line, start_column, node_type, name) 去重
    const relevantAstNodes = allAstNodes.filter((n: any) => involvedNodeIds.has(n.id));
    const seen = new Set<string>();
    const deduped: any[] = [];
    for (const node of relevantAstNodes) {
      const key = `${node.fileId}_${node.startLine}_${node.startColumn}_${node.nodeType}_${node.name}`;
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push(node);
      }
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      const result = await buildGraphData(deduped, callEdges, fileId);
      if (!cancelled) {
        setGraphData(result);
      }
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fileId, allAstNodes, callEdges]);

  // useMemo 必须在早期 return 之前调用
  const { nodes: displayedNodes, edges: displayedEdges } = useMemo(() => {
    if (!graphData || !focusedNodeId) {
      return { nodes: graphData?.nodes || [], edges: graphData?.edges || [] };
    }
    const connectedEdgeIds = new Set<string>();
    const connectedNodeIds = new Set<string>();
    for (const edge of graphData.edges) {
      if (edge.source === focusedNodeId || edge.target === focusedNodeId) {
        connectedEdgeIds.add(edge.id);
        connectedNodeIds.add(edge.source);
        connectedNodeIds.add(edge.target);
      }
    }
    const dimmedNodes = graphData.nodes.map((node) => ({
      ...node,
      style: { ...node.style, opacity: connectedNodeIds.has(node.id) || node.id === focusedNodeId ? 1 : 0.15 },
    }));
    const dimmedEdges = graphData.edges.map((edge) => ({
      ...edge,
      style: { ...edge.style, opacity: connectedEdgeIds.has(edge.id) ? 1 : 0.1, strokeWidth: connectedEdgeIds.has(edge.id) ? 3 : 1 },
    }));
    return { nodes: dimmedNodes, edges: dimmedEdges };
  }, [graphData, focusedNodeId]);

  // 边 hover 事件：显示标签
  const onEdgeMouseEnter = useCallback((_: React.MouseEvent, edge: Edge) => {
    setHoveredEdgeId(edge.id);
  }, []);

  const onEdgeMouseLeave = useCallback(() => {
    setHoveredEdgeId(null);
  }, []);

  // 应用 hover 状态到边：hover 的边显示标签（含调用次数）
  const finalEdges: Edge[] = useMemo(() => {
    return displayedEdges.map((edge: Edge) => {
      if (hoveredEdgeId === edge.id && edge.data?.callName) {
        const callCount = (edge.data?.callCount as number | undefined) || 1;
        const label = callCount > 1 ? `${edge.data.callName} ×${callCount}` : edge.data.callName;
        return {
          ...edge,
          label,
          labelStyle: {
            fontSize: 10,
            fontWeight: 600,
            fill: "#ffffff",
            backgroundColor: "#1f2937",
            opacity: 1,
          },
          labelBgStyle: { fill: "#1f2937", fillOpacity: 1 },
          labelBgPadding: [4, 8],
          labelBgBorderRadius: 10,
        } as Edge;
      }
      return edge;
    });
  }, [displayedEdges, hoveredEdgeId]);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setFocusedNodeId((prev) => (prev === node.id ? null : node.id));
  }, []);

  const onPaneClick = useCallback(() => setFocusedNodeId(null), []);

  const edgeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const edge of displayedEdges) {
      const type = edge.style?.strokeDasharray === "5,5" ? "dynamic"
        : edge.style?.strokeDasharray === "2,3" ? "unknown"
        : "static";
      counts[type] = (counts[type] || 0) + 1;
    }
    return counts;
  }, [displayedEdges]);

  return (
    <div className="h-full flex flex-col">
      {isLoading ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm text-[var(--text-muted)]">加载调用图...</p>
          </div>
        </div>
      ) : !graphData || graphData.nodes.length === 0 ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center text-[var(--text-muted)]">
            <p className="text-sm">该文件暂无调用关系</p>
          </div>
        </div>
      ) : (
        <>
          {/* 顶部工具栏 */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border)] bg-white/50 backdrop-blur flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              {focusedNodeId && (
                <>
                  <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">聚焦模式</span>
                  <button
                    onClick={() => setSelectedNodeForChain(focusedNodeId)}
                    className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors font-medium whitespace-nowrap"
                  >
                    🔗 查看调用链
                  </button>
                  <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">· 点击空白区域退出</span>
                </>
              )}
              {!focusedNodeId && (
                <span className="text-xs text-[var(--text-muted)]">点击节点查看详情 · 悬停边查看调用名</span>
              )}
            </div>
            <LegendDropdown edgeCounts={edgeCounts} />
          </div>

          {/* ReactFlow 图 */}
          <div className="flex-1">
            <ReactFlow
              nodes={displayedNodes}
              edges={finalEdges}
              nodeTypes={nodeTypes}
              onNodeClick={onNodeClick}
              onPaneClick={onPaneClick}
              onEdgeMouseEnter={onEdgeMouseEnter}
              onEdgeMouseLeave={onEdgeMouseLeave}
              fitView
              minZoom={0.1}
              maxZoom={3}
              defaultViewport={{ x: 0, y: 0, zoom: 0.65 }}
            >
              <Background color="#e5e7eb" gap={16} />
              <Controls />
              <MiniMap
                pannable
                zoomable
                nodeColor={(node) => {
                  const nodeType = (node.data as any)?.nodeType || "function";
                  return NODE_TYPE_CONFIG[nodeType]?.color || "#6b7280";
                }}
              />
            </ReactFlow>
          </div>

          {/* 调用链面板 Modal */}
          {selectedNodeForChain && chainNodeData && (
            <CallChainPanel
              nodeId={chainNodeData.id}
              nodeName={chainNodeData.name}
              nodeType={chainNodeData.nodeType}
              filePath={chainNodeData.filePath}
              onClose={() => setSelectedNodeForChain(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
