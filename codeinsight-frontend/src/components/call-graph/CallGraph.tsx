/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

/*
 * 调用类型说明：
 * - static:    静态调用（实线，蓝色）
 * - dynamic:   动态调用（虚线，黄色）
 * - unknown:   未知调用类型（点线，灰色）
 * - external:  外部调用（虚线，绿色），表示对外部模块/服务的调用
 * - injected:  依赖注入调用（点线，紫色），表示通过 IoC 容器注入的调用
 */

import React, { useCallback, useMemo, useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
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

const NODE_ENTER_DURATION = 0.28;
const NODE_EXIT_DURATION = 0.22;
const NODE_POSITION_TRANSITION = 350;

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
  external: { color: "#10b981", borderColor: "#059669", label: "外部", icon: "E" },
};

const NODE_W = 140;
const NODE_H = 56;

/** 每次点击 ▼/▲ 按钮展开的外部节点数上限（参考 CallChainPanel 的 BFS 逻辑） */
const MAX_EXTERNAL_PER_EXPANSION = 8;
/** 整张图总节点数上限 */
const MAX_TOTAL_NODES = 120;

const CALL_TYPE_STYLES: Record<string, { stroke: string; strokeDasharray: string; width: number }> = {
  static: { stroke: "#60a5fa", strokeDasharray: "0", width: 2 },
  dynamic: { stroke: "#fbbf24", strokeDasharray: "5,5", width: 2 },
  unknown: { stroke: "#9ca3af", strokeDasharray: "2,3", width: 1 },
  external: { stroke: "#10b981", strokeDasharray: "3,3", width: 2 },
  injected: { stroke: "#a855f7", strokeDasharray: "1,2", width: 2 },
};

const CLASS_TYPES = new Set(["class"]);
const MEMBER_TYPES = new Set(["function", "method", "constructor"]);
const MAX_HANDLES = 6;

const elk = new ELKConstructor({
  defaultLayoutOptions: {
    "elk.algorithms.layered": "true",
    "elk.layered.spacing.nodeNodeBetweenLayers": "70",
    "elk.layered.spacing.nodeNodeWithinLayers": "30",
    "elk.layered.spacing.edgeNodeBetweenLayers": "20",
    "elk.spacing.nodeNode": "20",
    "elk.direction": "DOWN",
    "elk.unflatten": "true",
    "elk.layered.unflatten.maxDegree": "1",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
    "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED",
    "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH",
    "elk.aspectRatio": "1.6",
    "elk.padding": "[top=20,left=20,bottom=20,right=20]",
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
  if (data.pendingFwd > 0) lines.push(`▼ 待展开外部调用：${data.pendingFwd}`);
  if (data.pendingBwd > 0) lines.push(`▲ 待展开外部调用者：${data.pendingBwd}`);
  if (data.expandedFwdCount > 0) lines.push(`▼ 已展开 ${data.expandedFwdCount} 个调用（点击折叠）`);
  if (data.expandedBwdCount > 0) lines.push(`▲ 已展开 ${data.expandedBwdCount} 个调用者（点击折叠）`);
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
 * 小型展开/折叠按钮：▼ 向下（callee）/ ▲ 向上（caller）
 *
 * 状态：
 * - 蓝色 + 数字：有 N 个待展开，点击展开
 * - 红色 + 数字：已展开 N 个，点击折叠（原路按步折叠）
 * - 不显示：既无待展开也无已展开
 */
function ToggleButton({
  direction,
  pendingCount,
  expandedCount,
  onClick,
}: {
  direction: "down" | "up";
  pendingCount: number;
  expandedCount: number;
  onClick: (e: React.MouseEvent) => void;
}) {
  if (pendingCount === 0 && expandedCount === 0) return null;

  const isExpanded = expandedCount > 0 && pendingCount === 0;
  const isPartial = pendingCount > 0 && expandedCount > 0;
  const color = isExpanded ? "#ef4444" : isPartial ? "#f59e0b" : "#3b82f6";
  const icon = direction === "down" ? "▼" : "▲";
  const title = direction === "down"
    ? (isExpanded
      ? `已展开 ${expandedCount} 个外部调用，点击折叠（原路按步折叠）`
      : `待展开 ${pendingCount} 个外部调用${expandedCount > 0 ? `（已展开 ${expandedCount}）` : ""}，点击展开（本次最多 ${MAX_EXTERNAL_PER_EXPANSION} 个）`)
    : (isExpanded
      ? `已展开 ${expandedCount} 个外部调用者，点击折叠（原路按步折叠）`
      : `待展开 ${pendingCount} 个外部调用者${expandedCount > 0 ? `（已展开 ${expandedCount}）` : ""}，点击展开（本次最多 ${MAX_EXTERNAL_PER_EXPANSION} 个）`);

  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        onClick(e);
      }}
      className="absolute flex items-center justify-center rounded-full text-[9px] font-bold cursor-pointer hover:scale-110 transition-transform z-20"
      style={{
        backgroundColor: color,
        color: "#ffffff",
        border: "1.5px solid #ffffff",
        boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        width: 18,
        height: 18,
        [direction === "down" ? "bottom" : "top"]: -8,
        right: -8,
      }}
      title={title}
    >
      <span style={{ fontSize: 8, lineHeight: 1 }}>{icon}</span>
      <span style={{ fontSize: 8, lineHeight: 1, marginLeft: 1 }}>
        {isExpanded ? expandedCount : pendingCount}
      </span>
    </div>
  );
}

/**
 * 自定义 CallGraph 节点 — 渲染多个 Handle + tooltip + ▼/▲ 双向按钮
 */
function CallGraphNode({ data, selected }: any) {
  const [hovered, setHovered] = useState(false);
  const isClass = data.isClass;
  const isMember = data.isMember;
  const isExiting = data.isExiting;

  // 调用点节点：极简样式，只作为边连接点
  if (data.isCallSite) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.85 }}
        transition={{
          duration: isExiting ? NODE_EXIT_DURATION : NODE_ENTER_DURATION,
          ease: "easeOut",
        }}
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
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85, y: -8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.85, y: -8 }}
      transition={{
        duration: isExiting ? NODE_EXIT_DURATION : NODE_ENTER_DURATION,
        ease: "easeOut",
      }}
      className="relative px-3 py-2 text-center font-medium cursor-pointer"
      style={{
        backgroundColor: data.isCurrentFile
          ? (isClass ? "rgba(236, 72, 153, 0.15)" : data.color)
          : "rgba(107, 114, 128, 0.25)",
        borderColor: selected ? "#3b82f6" : (data.isCurrentFile ? data.borderColor : "#6b7280"),
        borderWidth: selected ? 3 : (isClass ? 2 : isMember ? 2.5 : 2),
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
        boxShadow: selected ? "0 0 0 2px rgba(59, 130, 246, 0.3)" : "none",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* ▼ 向下展开/折叠按钮（callee 方向） */}
      <ToggleButton
        direction="down"
        pendingCount={data.pendingFwd || 0}
        expandedCount={data.expandedFwdCount || 0}
        onClick={data.onToggleFwd}
      />
      {/* ▲ 向上展开/折叠按钮（caller 方向） */}
      <ToggleButton
        direction="up"
        pendingCount={data.pendingBwd || 0}
        expandedCount={data.expandedBwdCount || 0}
        onClick={data.onToggleBwd}
      />

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
    </motion.div>
  );
}

const nodeTypes = { callNode: CallGraphNode };

/**
 * 构建完整的图数据（含当前文件节点和外部 callee 节点）。
 *
 * 设计要点：
 * - ELK 一次性布局所有节点（含外部 callee），位置稳定不抖动
 * - 渲染时默认只显示当前文件节点；外部 callee 通过 ▼ 按钮按需展开
 * - 外部 caller 通过 ▲ 按钮调用 API 按需获取并展开
 */
async function buildGraphData(
  astNodes: any[],
  callEdges: any[],
  currentFileId?: string,
): Promise<{
  nodes: Node[];
  edges: Edge[];
  externalCalleesByCaller: Map<string, string[]>;
  astNodeMap: Map<string, any>;
}> {
  if (!astNodes.length || !callEdges.length) {
    return { nodes: [], edges: [], externalCalleesByCaller: new Map(), astNodeMap: new Map() };
  }

  const callableTypes = new Set(["function", "method", "constructor", "class", "interface", "enum", "struct"]);
  const callableNodes = astNodes.filter((n: any) => callableTypes.has(n.nodeType));

  const nodeMap = new Map<string, any>();
  callableNodes.forEach((n: any) => nodeMap.set(n.id, n));

  // 扩展 nodeMap：当前文件的 call 节点也加入
  const currentFileCallNodes = currentFileId
    ? astNodes.filter((n: any) => n.nodeType === "call" && n.fileId === currentFileId)
    : [];
  currentFileCallNodes.forEach((n: any) => nodeMap.set(n.id, n));

  // 只保留两端的节点都在 nodeMap 中的边
  const validEdges = callEdges.filter((e: any) => e.calleeNodeId && nodeMap.has(e.callerNodeId) && nodeMap.has(e.calleeNodeId));

  if (validEdges.length === 0) {
    return { nodes: [], edges: [], externalCalleesByCaller: new Map(), astNodeMap: nodeMap };
  }

  // === 按 (caller, callee) 合并重复边 ===
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

  const uniqueEdges = Array.from(uniqueEdgeMap.values()).map(({ count, edge }) => ({ ...edge, callCount: count }));

  // 统计出度/入度
  const outDegree = new Map<string, number>();
  const inDegree = new Map<string, number>();
  for (const edge of uniqueEdges) {
    outDegree.set(edge.callerNodeId, (outDegree.get(edge.callerNodeId) || 0) + 1);
    inDegree.set(edge.calleeNodeId, (inDegree.get(edge.calleeNodeId) || 0) + 1);
  }

  // 收集边涉及的节点
  const involvedNodeIds = new Set<string>();
  for (const edge of uniqueEdges) {
    involvedNodeIds.add(edge.callerNodeId);
    involvedNodeIds.add(edge.calleeNodeId);
  }

  // === 构建外部 callee 索引：每个 caller 节点对应的外部 callee id 列表 ===
  const externalCalleesByCaller = new Map<string, string[]>();
  for (const edge of uniqueEdges) {
    const callerNode = nodeMap.get(edge.callerNodeId);
    const calleeNode = nodeMap.get(edge.calleeNodeId);
    if (!callerNode || !calleeNode) continue;

    const isExternalCallee = calleeNode.fileId !== currentFileId;
    if (isExternalCallee) {
      const list = externalCalleesByCaller.get(edge.callerNodeId) || [];
      if (!list.includes(edge.calleeNodeId)) {
        list.push(edge.calleeNodeId);
        externalCalleesByCaller.set(edge.callerNodeId, list);
      }
    }
  }

  // 构建 ELK 输入
  const elkNodes: Array<{ id: string; width: number; height: number; label?: string }> = [];
  const elkEdges: Array<{ id: string; sources: string[]; targets: string[]; label?: string }> = [];

  for (const nodeId of involvedNodeIds) {
    const node = nodeMap.get(nodeId);
    if (!node) continue;
    const isCallNode = node.nodeType === "call";
    elkNodes.push({
      id: node.id,
      width: isCallNode ? 80 : NODE_W,
      height: isCallNode ? 28 : NODE_H,
      label: node.name,
    });
  }

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
          pendingFwd: 0,
          pendingBwd: 0,
          expandedFwdCount: 0,
          expandedBwdCount: 0,
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
        pendingFwd: 0,
        pendingBwd: 0,
        expandedFwdCount: 0,
        expandedBwdCount: 0,
      },
    });
  }

  // 构建边
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
      label: undefined,
      labelStyle: { opacity: 0 },
      labelBgStyle: { opacity: 0 },
      data: { callName: edge.callName, callCount: edge.callCount },
      markerEnd: { type: "arrowclosed", width: 10, height: 10, color: style.stroke },
    });
  }

  return { nodes: graphNodes, edges: graphEdges, externalCalleesByCaller, astNodeMap: nodeMap };
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
              <div>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">交互说明</p>
                <div className="space-y-1">
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-500">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "#3b82f6", color: "#fff", width: 16, height: 16 }}>▼N</span>
                    <span>蓝色 ▼N：N 个外部调用可展开</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-500">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "#ef4444", color: "#fff", width: 16, height: 16 }}>▼N</span>
                    <span>红色 ▼N：已展开 N 个，点击折叠</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-500">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "#3b82f6", color: "#fff", width: 16, height: 16 }}>▲N</span>
                    <span>蓝色 ▲N：N 个外部调用者可展开</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-500">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "#ef4444", color: "#fff", width: 16, height: 16 }}>▲N</span>
                    <span>红色 ▲N：已展开 N 个，点击折叠</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-gray-500">
                    <span className="text-[10px] flex-shrink-0">点击节点</span>
                    <span>切换聚焦模式</span>
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
  // 用 repository_id 查所有 AST 节点
  const { data: allAstNodes, isLoading: astLoading } = useAstNodes({ repository_id: repositoryId });

  const isLoading = astLoading || edgesLoading;
  const [graphData, setGraphData] = useState<{
    nodes: Node[];
    edges: Edge[];
    externalCalleesByCaller: Map<string, string[]>;
    astNodeMap: Map<string, any>;
  } | null>(null);
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [selectedNodeForChain, setSelectedNodeForChain] = useState<string | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);

  /**
   * 双向展开状态（参考 CallChainPanel 的 BFS 设计）：
   *
   * - expandedFwdByNode: 每个节点已展开的外部 callee 集合（向下）
   * - expandedBwdByNode: 每个节点已展开的外部 caller 集合（向上）
   * - pendingFwdByNodeRef: 每个节点的待展开外部 callee 队列（基于已有数据）
   * - pendingBwdByNodeRef: 每个节点的待展开外部 caller 队列（API 获取）
   * - externalCallerNodes: API 获取的外部 caller 节点数据
   * - externalCallerEdges: API 获取的外部 caller 边
   * - externalCallersLoadedRef: 已通过 API 获取外部 caller 的节点集合
   */
  const [expandedFwdByNode, setExpandedFwdByNode] = useState<Map<string, Set<string>>>(new Map());
  const [expandedBwdByNode, setExpandedBwdByNode] = useState<Map<string, Set<string>>>(new Map());
  const [exitingNodeIds, setExitingNodeIds] = useState<Set<string>>(new Set());
  const pendingFwdByNodeRef = useRef<Map<string, string[]>>(new Map());
  const pendingBwdByNodeRef = useRef<Map<string, string[]>>(new Map());
  const [externalCallerNodes, setExternalCallerNodes] = useState<Map<string, any>>(new Map());
  const [externalCallerEdges, setExternalCallerEdges] = useState<Map<string, Edge>>(new Map());
  const externalCallersLoadedRef = useRef<Set<string>>(new Set());
  const isMountedRef = useRef(true);
  const exitTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

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
      setExpandedFwdByNode(new Map());
      setExpandedBwdByNode(new Map());
      pendingFwdByNodeRef.current = new Map();
      pendingBwdByNodeRef.current = new Map();
      setExternalCallerNodes(new Map());
      setExternalCallerEdges(new Map());
      externalCallersLoadedRef.current = new Set();
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
      if (!cancelled && isMountedRef.current) {
        setGraphData(result);
        // 初始化 pendingFwdByNode：每个 caller 的全部外部 callee 都视为待展开
        pendingFwdByNodeRef.current = new Map(result.externalCalleesByCaller);
        setExpandedFwdByNode(new Map());
        setExpandedBwdByNode(new Map());
        pendingBwdByNodeRef.current = new Map();
        setExternalCallerNodes(new Map());
        setExternalCallerEdges(new Map());
        externalCallersLoadedRef.current = new Set();
        setGlobalError(null);
      }
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fileId, allAstNodes, callEdges]);

  /**
   * 递归折叠 fwd 子树：移除 nodeId 的所有 fwd 后代（包括后代的后代）
   */
  const collapseFwdRecursive = useCallback((map: Map<string, Set<string>>, nodeId: string) => {
    const children = map.get(nodeId);
    if (!children) return;
    // 递归折叠每个子节点的 fwd 子树
    for (const childId of children) {
      collapseFwdRecursive(map, childId);
    }
    map.delete(nodeId);
  }, []);

  /**
   * 递归折叠 bwd 子树：移除 nodeId 的所有 bwd 后代
   */
  const collapseBwdRecursive = useCallback((map: Map<string, Set<string>>, nodeId: string) => {
    const parents = map.get(nodeId);
    if (!parents) return;
    for (const parentId of parents) {
      collapseBwdRecursive(map, parentId);
    }
    map.delete(nodeId);
  }, []);

  /**
   * 计算所有已展开的外部节点总数
   */
  const countAllExpanded = useCallback((fwd: Map<string, Set<string>>, bwd: Map<string, Set<string>>): number => {
    let count = 0;
    for (const set of fwd.values()) count += set.size;
    for (const set of bwd.values()) count += set.size;
    return count;
  }, []);

  /**
   * 计算 displayedNodeCount（用于上限检查）
   */
  const displayedNodeCount = useMemo(() => {
    if (!graphData) return 0;
    const currentFileNodes = graphData.nodes.filter((n) => {
      const d = n.data as any;
      return d?.isCurrentFile || d?.isCallSite;
    });
    let count = currentFileNodes.length;
    for (const set of expandedFwdByNode.values()) count += set.size;
    for (const set of expandedBwdByNode.values()) count += set.size;
    return count;
  }, [graphData, expandedFwdByNode, expandedBwdByNode]);

  /**
   * 收集 fwd 方向所有后代节点 ID（递归）
   */
  const collectFwdDescendants = useCallback((fwdMap: Map<string, Set<string>>, nodeId: string): Set<string> => {
    const result = new Set<string>();
    const children = fwdMap.get(nodeId);
    if (!children) return result;
    for (const childId of children) {
      result.add(childId);
      const sub = collectFwdDescendants(fwdMap, childId);
      for (const id of sub) result.add(id);
    }
    return result;
  }, []);

  /**
   * 收集 bwd 方向所有后代节点 ID（递归）
   */
  const collectBwdDescendants = useCallback((bwdMap: Map<string, Set<string>>, nodeId: string): Set<string> => {
    const result = new Set<string>();
    const parents = bwdMap.get(nodeId);
    if (!parents) return result;
    for (const parentId of parents) {
      result.add(parentId);
      const sub = collectBwdDescendants(bwdMap, parentId);
      for (const id of sub) result.add(id);
    }
    return result;
  }, []);

  /**
   * 启动节点退出动画，延迟后真正移除
   */
  const startExitAnimation = useCallback((nodeIds: Set<string>, onComplete: () => void) => {
    if (nodeIds.size === 0) {
      onComplete();
      return;
    }

    setExitingNodeIds((prev) => {
      const next = new Set(prev);
      for (const id of nodeIds) next.add(id);
      return next;
    });

    const timer = setTimeout(() => {
      setExitingNodeIds((prev) => {
        const next = new Set(prev);
        for (const id of nodeIds) next.delete(id);
        return next;
      });
      exitTimersRef.current.delete("batch");
      onComplete();
    }, NODE_EXIT_DURATION * 1000 + 20);

    exitTimersRef.current.set("batch", timer);
  }, []);

  /**
   * 向下展开/折叠 toggle（callee 方向，基于已有数据）
   *
   * - 有 pending：批量展开最多 MAX_EXTERNAL_PER_EXPANSION 个外部 callee
   * - 已展开（无 pending）：折叠该节点的 fwd 子树（原路按步折叠，带退出动画）
   */
  const toggleFwd = useCallback((nodeId: string) => {
    const pending = pendingFwdByNodeRef.current.get(nodeId) || [];
    const remaining = pending.filter(id => !((expandedFwdByNode.get(nodeId) || new Set()).has(id)));

    if (remaining.length > 0) {
      // 展开
      setExpandedFwdByNode((prev) => {
        const next = new Map(prev);
        const current = new Set(next.get(nodeId) || []);
        const totalAfterExpand = countAllExpanded(next, expandedBwdByNode) + displayedNodeCount;
        const allowed = Math.min(
          MAX_EXTERNAL_PER_EXPANSION,
          remaining.length,
          Math.max(0, MAX_TOTAL_NODES - totalAfterExpand)
        );
        if (allowed <= 0) {
          setGlobalError(`已达节点数上限（${MAX_TOTAL_NODES}），请先折叠部分节点`);
          return prev;
        }
        for (let i = 0; i < allowed; i++) {
          current.add(remaining[i]);
        }
        next.set(nodeId, current);
        return next;
      });
      setGlobalError(null);
      return;
    }

    // 折叠（原路按步折叠）：先收集所有后代，播放退出动画，再真正移除
    const toRemove = collectFwdDescendants(expandedFwdByNode, nodeId);
    // 直接子节点也要移除
    const directChildren = expandedFwdByNode.get(nodeId);
    if (directChildren) for (const id of directChildren) toRemove.add(id);

    startExitAnimation(toRemove, () => {
      setExpandedFwdByNode((prev) => {
        const next = new Map(prev);
        collapseFwdRecursive(next, nodeId);
        return next;
      });
    });
  }, [expandedFwdByNode, expandedBwdByNode, displayedNodeCount, countAllExpanded, collapseFwdRecursive, collectFwdDescendants, startExitAnimation]);

  /**
   * 向上展开/折叠 toggle（caller 方向，需 API 调用）
   *
   * - 首次：调用 getCallers API 获取外部 caller，存入 pendingBwdByNodeRef
   * - 有 pending：批量展开最多 MAX_EXTERNAL_PER_EXPANSION 个外部 caller
   * - 已展开（无 pending）：折叠该节点的 bwd 子树（原路按步折叠，递归移除后代）
   */
  const toggleBwd = useCallback(async (nodeId: string) => {
    // 首次：调用 API 获取外部 caller
    if (!externalCallersLoadedRef.current.has(nodeId)) {
      externalCallersLoadedRef.current.add(nodeId);
      try {
        const { getCallers } = await import("@/api/call-edges");
        const callers = await getCallers(nodeId).catch((e) => {
          console.error("getCallers error:", e);
          return [];
        }) as any[];

        // 后端返回 snake_case 字段：edge_id, call_name, call_type, caller { id, name, node_type, file_path }
        // 过滤掉当前文件内的 caller（已在图中显示）
        const externalCallers = callers.filter((item: any) => {
          const caller = item.caller;
          if (!caller) return false;
          // 外部 caller：不在当前 graphData 节点中（即不在当前文件内）
          return !graphData?.astNodeMap.has(caller.id);
        });

        // 存入 pendingBwdByNodeRef
        const externalCallerIds = externalCallers.map((item: any) => item.caller?.id).filter(Boolean) as string[];
        pendingBwdByNodeRef.current.set(nodeId, externalCallerIds);

        // 存入 externalCallerNodes 和 externalCallerEdges
        if (externalCallers.length > 0 && isMountedRef.current) {
          setExternalCallerNodes((prev) => {
            const next = new Map(prev);
            for (const item of externalCallers) {
              const caller = item.caller;
              if (caller) {
                next.set(caller.id, caller);
              }
            }
            return next;
          });
          setExternalCallerEdges((prev) => {
            const next = new Map(prev);
            for (const item of externalCallers) {
              const caller = item.caller;
              if (caller) {
                const edgeId = `bwd-${caller.id}-${nodeId}`;
                const style = CALL_TYPE_STYLES[item.call_type] || CALL_TYPE_STYLES.unknown;
                next.set(edgeId, {
                  id: edgeId,
                  source: caller.id,
                  target: nodeId,
                  type: "smoothstep",
                  animated: item.call_type === "dynamic",
                  style: {
                    stroke: style.stroke,
                    strokeDasharray: style.strokeDasharray,
                    strokeWidth: style.width,
                  },
                  label: undefined,
                  labelStyle: { opacity: 0 },
                  labelBgStyle: { opacity: 0 },
                  data: { callName: item.call_name, callCount: 1 },
                  markerEnd: { type: "arrowclosed", width: 10, height: 10, color: style.stroke },
                });
              }
            }
            return next;
          });
        }
      } catch (e) {
        console.error("toggleBwd fetch error:", e);
        externalCallersLoadedRef.current.delete(nodeId);
        setGlobalError("获取外部调用者失败");
        return;
      }
    }

    const pending = pendingBwdByNodeRef.current.get(nodeId) || [];
    const currentExpanded = expandedBwdByNode.get(nodeId) || new Set();
    const remaining = pending.filter(id => !currentExpanded.has(id));

    if (remaining.length > 0) {
      // 展开
      setExpandedBwdByNode((prev) => {
        const next = new Map(prev);
        const current = new Set(next.get(nodeId) || []);
        const totalAfterExpand = countAllExpanded(expandedFwdByNode, next) + displayedNodeCount;
        const allowed = Math.min(
          MAX_EXTERNAL_PER_EXPANSION,
          remaining.length,
          Math.max(0, MAX_TOTAL_NODES - totalAfterExpand)
        );
        if (allowed <= 0) {
          setGlobalError(`已达节点数上限（${MAX_TOTAL_NODES}），请先折叠部分节点`);
          return prev;
        }
        for (let i = 0; i < allowed; i++) {
          current.add(remaining[i]);
        }
        next.set(nodeId, current);
        return next;
      });
      setGlobalError(null);
      return;
    }

    // 折叠（原路按步折叠）：先收集所有后代，播放退出动画，再真正移除
    const toRemove = collectBwdDescendants(expandedBwdByNode, nodeId);
    const directParents = expandedBwdByNode.get(nodeId);
    if (directParents) for (const id of directParents) toRemove.add(id);

    startExitAnimation(toRemove, () => {
      setExpandedBwdByNode((prev) => {
        const next = new Map(prev);
        collapseBwdRecursive(next, nodeId);
        return next;
      });
    });
  }, [graphData, expandedFwdByNode, expandedBwdByNode, displayedNodeCount, countAllExpanded, collapseBwdRecursive, collectBwdDescendants, startExitAnimation]);

  /**
   * 计算每个节点的 pendingFwd/pendingBwd/expandedFwdCount/expandedBwdCount，
   * 并决定渲染哪些节点和边。
   *
   * 渲染策略（参考 CallChainPanel 的按需加载）：
   * - 默认只渲染当前文件节点 + 当前文件内部边
   * - 当前文件节点上的外部 callee 显示为 ▼N 徽章
   * - 当前文件节点上的外部 caller 显示为 ▲N 徽章
   * - 已展开的外部节点正常渲染
   * - 总节点数不超过 MAX_TOTAL_NODES
   */
  const { nodes: displayedNodes, edges: displayedEdges } = useMemo(() => {
    if (!graphData) {
      return { nodes: [], edges: [] };
    }

    // 计算每个节点的 pending/expanded 计数
    const pendingFwdByNode = new Map<string, number>();
    const pendingBwdByNode = new Map<string, number>();
    const expandedFwdCountByNode = new Map<string, number>();
    const expandedBwdCountByNode = new Map<string, number>();

    for (const [callerId, allCallees] of pendingFwdByNodeRef.current) {
      const expanded = expandedFwdByNode.get(callerId) || new Set();
      const remaining = allCallees.filter(id => !expanded.has(id));
      pendingFwdByNode.set(callerId, remaining.length);
      expandedFwdCountByNode.set(callerId, expanded.size);
    }

    for (const [callerId, allCallers] of pendingBwdByNodeRef.current) {
      const expanded = expandedBwdByNode.get(callerId) || new Set();
      const remaining = allCallers.filter(id => !expanded.has(id));
      pendingBwdByNode.set(callerId, remaining.length);
      expandedBwdCountByNode.set(callerId, expanded.size);
    }

    // 聚焦模式：只显示聚焦节点 + 直接邻居
    if (focusedNodeId) {
      const connectedEdgeIds = new Set<string>();
      const connectedNodeIds = new Set<string>([focusedNodeId]);
      for (const edge of graphData.edges) {
        if (edge.source === focusedNodeId || edge.target === focusedNodeId) {
          connectedEdgeIds.add(edge.id);
          connectedNodeIds.add(edge.source);
          connectedNodeIds.add(edge.target);
        }
      }
      const filteredNodes = graphData.nodes.filter((node) => connectedNodeIds.has(node.id));
      const filteredEdges = graphData.edges.filter((edge) => connectedEdgeIds.has(edge.id));
      return { nodes: filteredNodes, edges: filteredEdges };
    }

    // 非聚焦模式：渲染当前文件节点 + 已展开的外部节点 + 正在退出的节点
    const visibleNodeIds = new Set<string>();
    for (const node of graphData.nodes) {
      const data = node.data as any;
      if (data?.isCurrentFile || data?.isCallSite) {
        visibleNodeIds.add(node.id);
      }
    }
    // 加入 fwd 已展开的外部 callee
    for (const set of expandedFwdByNode.values()) {
      for (const id of set) visibleNodeIds.add(id);
    }
    // 加入 bwd 已展开的外部 caller
    for (const set of expandedBwdByNode.values()) {
      for (const id of set) visibleNodeIds.add(id);
    }
    // 加入正在退出动画中的节点（播放退出动画后才真正移除）
    for (const id of exitingNodeIds) visibleNodeIds.add(id);

    // 构建外部 caller 节点的 ELK 位置（如果没有，用默认位置）
    // 注意：外部 caller 节点不在 graphData.nodes 中，需要单独创建
    const externalCallerNodeIds = new Set<string>();
    for (const set of expandedBwdByNode.values()) {
      for (const id of set) externalCallerNodeIds.add(id);
    }
    // 退出中的外部 caller 节点也加入
    for (const id of exitingNodeIds) {
      if (externalCallerNodes.has(id)) externalCallerNodeIds.add(id);
    }

    // 构建完整节点列表
    const visibleNodes: Node[] = [];
    const positionTransitionStyle = {
      transition: `transform ${NODE_POSITION_TRANSITION}ms cubic-bezier(0.22, 1, 0.36, 1)`,
    };

    // 1. graphData 中已有的节点
    for (const node of graphData.nodes) {
      if (visibleNodeIds.has(node.id)) {
        const pendingFwd = pendingFwdByNode.get(node.id) || 0;
        const pendingBwd = pendingBwdByNode.get(node.id) || 0;
        const expandedFwdCount = expandedFwdCountByNode.get(node.id) || 0;
        const expandedBwdCount = expandedBwdCountByNode.get(node.id) || 0;
        const isExiting = exitingNodeIds.has(node.id);
        visibleNodes.push({
          ...node,
          style: { ...(node.style as object || {}), ...positionTransitionStyle },
          data: {
            ...node.data,
            pendingFwd,
            pendingBwd,
            expandedFwdCount,
            expandedBwdCount,
            isExiting,
            onToggleFwd: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleFwd(node.id);
            },
            onToggleBwd: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleBwd(node.id);
            },
          },
        });
      }
    }

    // 构建位置查找表：graphData 节点位置 + 已渲染的外部 caller 位置
    // 用于计算新加入的外部 caller 节点位置
    const positionMap = new Map<string, { x: number; y: number }>();
    for (const node of graphData.nodes) {
      positionMap.set(node.id, node.position);
    }

    // 构建 caller → targets 映射（基于 externalCallerEdges）
    // 外部 caller 边：source=caller.id（外部）, target=nodeId（当前文件节点）
    const callerToTargets = new Map<string, string[]>();
    for (const edge of externalCallerEdges.values()) {
      if (visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) {
        const list = callerToTargets.get(edge.source) || [];
        list.push(edge.target);
        callerToTargets.set(edge.source, list);
      }
    }

    // 按 target 分组 caller，便于水平排布同一 target 的多个 caller
    const targetToCallers = new Map<string, string[]>();
    for (const [callerId, targets] of callerToTargets) {
      // 取第一个 target 作为分组依据（外部 caller 通常只调用当前文件中的一个节点）
      const target = targets[0];
      const list = targetToCallers.get(target) || [];
      list.push(callerId);
      targetToCallers.set(target, list);
    }

    // 2. 外部 caller 节点（不在 graphData 中）
    for (const id of externalCallerNodeIds) {
      if (visibleNodeIds.has(id)) {
        const callerData = externalCallerNodes.get(id);
        if (callerData) {
          const config = NODE_TYPE_CONFIG[callerData.node_type] || NODE_TYPE_CONFIG.function;
          // 计算外部 caller 节点位置：基于其 target 节点位置，向上偏移并水平排布
          const targets = callerToTargets.get(id) || [];
          let pos: { x: number; y: number };
          if (targets.length > 0) {
            // 取所有 target 的平均位置
            const targetPositions = targets
              .map((t) => positionMap.get(t))
              .filter((p): p is { x: number; y: number } => !!p);
            if (targetPositions.length > 0) {
              const avgX = targetPositions.reduce((sum, p) => sum + p.x, 0) / targetPositions.length;
              const minY = Math.min(...targetPositions.map((p) => p.y));
              // 同一 target 的多个 caller 水平排布
              const siblings = targetToCallers.get(targets[0]) || [id];
              const idx = siblings.indexOf(id);
              const spread = (idx - (siblings.length - 1) / 2) * (NODE_W + 20);
              pos = { x: avgX + spread, y: minY - (NODE_H + 80) };
            } else {
              pos = { x: 0, y: -100 };
            }
          } else {
            pos = { x: 0, y: -100 };
          }
          // 缓存位置供后续 chained expansion 使用
          positionMap.set(id, pos);

          const isExiting = exitingNodeIds.has(id);
          visibleNodes.push({
            id,
            type: "callNode",
            position: pos,
            width: NODE_W,
            height: NODE_H,
            style: positionTransitionStyle,
            data: {
              label: callerData.name,
              nodeType: callerData.node_type,
              nodeTypeLabel: config.label,
              icon: config.icon,
              color: config.color,
              borderColor: config.borderColor,
              isClass: CLASS_TYPES.has(callerData.node_type),
              isMember: MEMBER_TYPES.has(callerData.node_type),
              isCurrentFile: false,
              filePath: callerData.file_path,
              callsMade: 0,
              callsReceived: 0,
              pendingFwd: pendingFwdByNode.get(id) || 0,
              pendingBwd: pendingBwdByNode.get(id) || 0,
              expandedFwdCount: expandedFwdCountByNode.get(id) || 0,
              expandedBwdCount: expandedBwdCountByNode.get(id) || 0,
              isExiting,
              onToggleFwd: (e: React.MouseEvent) => {
                e.stopPropagation();
                toggleFwd(id);
              },
              onToggleBwd: (e: React.MouseEvent) => {
                e.stopPropagation();
                toggleBwd(id);
              },
            },
          });
        }
      }
    }

    // 边：graphData.edges + externalCallerEdges，过滤两端都在 visibleNodeIds 中
    const visibleEdges: Edge[] = [];
    for (const edge of graphData.edges) {
      if (visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) {
        visibleEdges.push(edge);
      }
    }
    for (const edge of externalCallerEdges.values()) {
      if (visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) {
        visibleEdges.push(edge);
      }
    }

    return { nodes: visibleNodes, edges: visibleEdges };
  }, [graphData, focusedNodeId, expandedFwdByNode, expandedBwdByNode, exitingNodeIds, externalCallerNodes, externalCallerEdges, toggleFwd, toggleBwd]);

  // 边 hover 事件
  const onEdgeMouseEnter = useCallback((_: React.MouseEvent, edge: Edge) => {
    setHoveredEdgeId(edge.id);
  }, []);

  const onEdgeMouseLeave = useCallback(() => {
    setHoveredEdgeId(null);
  }, []);

  // 应用 hover 状态到边
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

  /**
   * 节点点击：切换聚焦模式
   * 注意：▼/▲ 按钮点击已通过 stopPropagation 阻止冒泡，不会触发此事件
   */
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    setFocusedNodeId((prev) => (prev === node.id ? null : node.id));
  }, []);

  /**
   * 节点右键：折叠该节点的所有展开（fwd + bwd）
   */
  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: Node) => {
    event.preventDefault();
    // 收集 fwd + bwd 两个方向的所有后代
    const fwdToRemove = collectFwdDescendants(expandedFwdByNode, node.id);
    const fwdDirect = expandedFwdByNode.get(node.id);
    if (fwdDirect) for (const id of fwdDirect) fwdToRemove.add(id);

    const bwdToRemove = collectBwdDescendants(expandedBwdByNode, node.id);
    const bwdDirect = expandedBwdByNode.get(node.id);
    if (bwdDirect) for (const id of bwdDirect) bwdToRemove.add(id);

    const allToRemove = new Set([...fwdToRemove, ...bwdToRemove]);

    startExitAnimation(allToRemove, () => {
      setExpandedFwdByNode((prev) => {
        const next = new Map(prev);
        collapseFwdRecursive(next, node.id);
        return next;
      });
      setExpandedBwdByNode((prev) => {
        const next = new Map(prev);
        collapseBwdRecursive(next, node.id);
        return next;
      });
    });
  }, [expandedFwdByNode, expandedBwdByNode, collapseFwdRecursive, collapseBwdRecursive, collectFwdDescendants, collectBwdDescendants, startExitAnimation]);

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

  // 统计总待展开数和已展开数（用于工具栏提示）
  const totalPending = useMemo(() => {
    let sum = 0;
    for (const [callerId, allCallees] of pendingFwdByNodeRef.current) {
      const expanded = expandedFwdByNode.get(callerId) || new Set();
      sum += allCallees.filter(id => !expanded.has(id)).length;
    }
    for (const [callerId, allCallers] of pendingBwdByNodeRef.current) {
      const expanded = expandedBwdByNode.get(callerId) || new Set();
      sum += allCallers.filter(id => !expanded.has(id)).length;
    }
    return sum;
  }, [expandedFwdByNode, expandedBwdByNode]);

  const totalExpanded = useMemo(() => {
    let sum = 0;
    for (const set of expandedFwdByNode.values()) sum += set.size;
    for (const set of expandedBwdByNode.values()) sum += set.size;
    return sum;
  }, [expandedFwdByNode, expandedBwdByNode]);

  // 一键折叠所有外部调用（带退出动画）
  const collapseAll = useCallback(() => {
    const allExpanded = new Set<string>();
    for (const set of expandedFwdByNode.values()) {
      for (const id of set) allExpanded.add(id);
    }
    for (const set of expandedBwdByNode.values()) {
      for (const id of set) allExpanded.add(id);
    }

    startExitAnimation(allExpanded, () => {
      setExpandedFwdByNode(new Map());
      setExpandedBwdByNode(new Map());
      setGlobalError(null);
    });
  }, [expandedFwdByNode, expandedBwdByNode, startExitAnimation]);

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
              {focusedNodeId ? (
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
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[var(--text-muted)]">
                    ▼ 展开调用 · ▲ 展开调用者 · 点击节点聚焦 · 右键收起全部
                  </span>
                  {totalExpanded > 0 && (
                    <button
                      onClick={collapseAll}
                      className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors font-medium whitespace-nowrap"
                    >
                      收起全部 ({totalExpanded})
                    </button>
                  )}
                  {totalPending > 0 && (
                    <span className="text-xs text-blue-500 whitespace-nowrap">
                      待展开: {totalPending}
                    </span>
                  )}
                </div>
              )}
            </div>
            <LegendDropdown edgeCounts={edgeCounts} />
          </div>

          {/* 全局错误提示 */}
          {globalError && (
            <div className="px-4 py-2 bg-amber-50 border-b border-amber-100 text-xs text-amber-700 flex items-center justify-between">
              <span>⚠ {globalError}</span>
              <button
                onClick={() => setGlobalError(null)}
                className="text-amber-500 hover:text-amber-700 ml-2"
              >✕</button>
            </div>
          )}

          {/* ReactFlow 图 */}
          <div className="flex-1">
            <ReactFlow
              nodes={displayedNodes}
              edges={finalEdges}
              nodeTypes={nodeTypes}
              onNodeClick={onNodeClick}
              onNodeContextMenu={onNodeContextMenu}
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
