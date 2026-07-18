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
  ReactFlowProvider,
  type Edge,
  type Node,
} from "@xyflow/react";
import Elk from "elkjs";
import { useAstNodes, useCallEdges } from "@/hooks/use-files";
import { CallChainPanel } from "./CallChainPanel";
import "@xyflow/react/dist/style.css";
import type { NavigableProps } from "@/components/analysis/NavTrailBar";

const NODE_ENTER_DURATION = 0.28;
const NODE_EXIT_DURATION = 0.22;
const NODE_POSITION_TRANSITION = 350;

const ELKConstructor = Elk;

interface CallGraphProps extends NavigableProps {
  fileId: string;
  repositoryId: string;
  highlightNodeId?: string;
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
    "elk.layered.spacing.nodeNodeBetweenLayers": "80",
    "elk.layered.spacing.nodeNodeWithinLayers": "45",
    "elk.layered.spacing.edgeNodeBetweenLayers": "25",
    "elk.spacing.nodeNode": "30",
    "elk.direction": "DOWN",
    "elk.unflatten": "true",
    "elk.layered.unflatten.maxDegree": "1",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
    "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED",
    "elk.layered.compaction.postCompaction.strategy": "NONE",
    "elk.aspectRatio": "1.4",
    "elk.padding": "[top=40,left=40,bottom=40,right=40]",
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
  loading,
  bwdChecked,
  hasPotentialExternal,
  totalAvailable,
}: {
  direction: "down" | "up";
  pendingCount: number;
  expandedCount: number;
  onClick: (e: React.MouseEvent) => void;
  loading?: boolean;
  bwdChecked?: boolean;
  /** 节点是否在预计算索引中有外部 caller（用于区分"无外部调用者"和"未检查"） */
  hasPotentialExternal?: boolean;
  /** 该方向总共有多少个外部节点（含已展开的），用于显示"全部"提示 */
  totalAvailable?: number;
}) {
  const isEmptyChecked = direction === "up" && bwdChecked && pendingCount === 0 && expandedCount === 0;
  // 预计算索引中也没有外部 caller → 隐藏按钮（不是"未检查"，而是真的没有）
  const hasNoExternalAtAll = direction === "up" && pendingCount === 0 && expandedCount === 0 && !bwdChecked && !hasPotentialExternal;
  if (isEmptyChecked || hasNoExternalAtAll) return null;
  // 无待展开、无已展开、非加载中 → 隐藏按钮
  if (!loading && pendingCount === 0 && expandedCount === 0) return null;

  const isExpanded = expandedCount > 0 && pendingCount === 0;
  const isPartial = pendingCount > 0 && expandedCount > 0;
  const color = isExpanded ? "var(--color-status-error)" : isPartial ? "var(--color-status-warning)" : loading ? "var(--text-muted)" : "var(--color-brand)";
  const icon = direction === "down" ? "▼" : "▲";
  let displayCount: string | number = isExpanded ? expandedCount : pendingCount;
  if (loading) {
    displayCount = "…";
  }

  // 构建标题：当待展开数 > 单次上限时，提示 Shift+Click 可展开全部
  const loadAllHint = totalAvailable && pendingCount > MAX_EXTERNAL_PER_EXPANSION
    ? `（Shift+点击展开全部 ${totalAvailable} 个）`
    : "";
  let title: string;
  if (direction === "down") {
    if (isExpanded) {
      title = `已展开 ${expandedCount} 个外部调用，点击折叠（原路按步折叠）`;
    } else {
      const extra = expandedCount > 0 ? `（已展开 ${expandedCount}）` : "";
      title = `待展开 ${pendingCount} 个外部调用${extra}，点击展开（本次最多 ${MAX_EXTERNAL_PER_EXPANSION} 个）${loadAllHint}`;
    }
  } else {
    if (isExpanded) {
      title = `已展开 ${expandedCount} 个外部调用者，点击折叠（原路按步折叠）`;
    } else if (loading) {
      title = "加载中...";
    } else {
      const extra = expandedCount > 0 ? `（已展开 ${expandedCount}）` : "";
      title = `待展开 ${pendingCount} 个外部调用者${extra}，点击展开（本次最多 ${MAX_EXTERNAL_PER_EXPANSION} 个）${loadAllHint}`;
    }
  }

  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        if (typeof onClick === "function" && !loading) onClick(e);
      }}
      className={`absolute flex items-center justify-center rounded-full text-[9px] font-bold ${loading ? "cursor-wait" : "cursor-pointer hover:scale-110"} transition-transform z-20 shadow-md`}
      style={{
        backgroundColor: color,
        color: "#ffffff",
        border: "1.5px solid hsla(0 0% 100% / 0.8)",
        width: 20,
        height: 20,
        [direction === "down" ? "bottom" : "top"]: -8,
        right: -8,
      }}
      title={title}
    >
      <span style={{ fontSize: 8, lineHeight: 1 }}>{icon}</span>
      <span style={{ fontSize: 8, lineHeight: 1, marginLeft: 1 }}>
        {displayCount}
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
          backgroundColor: "hsla(215 10% 47% / 0.08)",
          border: "1px dashed hsla(215 10% 47% / 0.3)",
          borderRadius: 4,
          fontSize: 10,
          color: "var(--text-muted)",
          fontWeight: 400,
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <span className="truncate px-1">{data.label}</span>
        {hovered && (
          <div
            className="absolute z-50 bottom-full left-1/2 mb-2 px-2 py-1 text-xs whitespace-nowrap rounded shadow-lg pointer-events-none"
            style={{ transform: "translateX(-50%)", backgroundColor: "var(--bg-card)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
          >
            {buildNodeTooltip(data)}
          </div>
        )}
        <Handle
          id="source-0"
          type="source"
          position={Position.Bottom}
          style={{ background: "var(--text-muted)", width: 6, height: 6 }}
        />
        <Handle
          id="target-0"
          type="target"
          position={Position.Top}
          style={{ background: "var(--text-muted)", width: 6, height: 6 }}
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
          ? (isClass ? "hsla(330 81% 60% / 0.15)" : data.color)
          : "hsla(215 10% 47% / 0.25)",
        borderColor: selected ? "var(--color-status-info)" : (data.isCurrentFile ? data.borderColor : "var(--border)"),
        borderWidth: selected ? 3 : (isClass ? 2 : isMember ? 2.5 : 2),
        borderStyle: data.isCurrentFile ? "solid" : "dashed",
        borderRadius: 10,
        color: "var(--text-primary)",
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
        boxShadow: selected ? "var(--glow-focus)" : "0 1px 3px rgba(0,0,0,0.08)",
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
        onClick={(e) => {
          if (e.shiftKey && data.onToggleBwdAll) {
            data.onToggleBwdAll(e);
          } else {
            data.onToggleBwd(e);
          }
        }}
        loading={data.bwdLoading}
        bwdChecked={data.bwdChecked}
        hasPotentialExternal={data.hasPotentialExternal}
        totalAvailable={data.totalAvailableBwd}
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
      {data.onNavigate && (
        <div className="flex gap-1 mt-0.5">
          <button
            onClick={(e) => {
              e.stopPropagation();
              data.onNavigate({ component: "structure", fileId: data.fileId, nodeId: data.label, label: data.label, detail: "代码结构" });
            }}
            className="text-[9px] px-1 py-0.5 rounded bg-brand/10 text-brand hover:bg-brand/20 transition-colors"
            title="查看代码结构"
          >
            ◆结构
          </button>
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
  onNavigate?: NavigableProps["onNavigate"],
): Promise<{
  nodes: Node[];
  edges: Edge[];
  externalCalleesByCaller: Map<string, string[]>;
  externalCallersByCallee: Map<string, string[]>;
  astNodeMap: Map<string, any>;
}> {
  if (!astNodes.length || !callEdges.length) {
    return { nodes: [], edges: [], externalCalleesByCaller: new Map(), externalCallersByCallee: new Map(), astNodeMap: new Map() };
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
    return { nodes: [], edges: [], externalCalleesByCaller: new Map(), externalCallersByCallee: new Map(), astNodeMap: nodeMap };
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
  // === 构建外部 caller 索引：每个 callee 节点对应的外部 caller id 列表（用于向上展开计数）===
  const externalCallersByCallee = new Map<string, string[]>();
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

    // 外部 caller：caller 不在当前文件，callee 在当前文件
    const isExternalCaller = callerNode.fileId !== currentFileId;
    if (isExternalCaller) {
      const list = externalCallersByCallee.get(edge.calleeNodeId) || [];
      if (!list.includes(edge.callerNodeId)) {
        list.push(edge.callerNodeId);
        externalCallersByCallee.set(edge.calleeNodeId, list);
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
          fileId: astNode.fileId,
          filePath: astNode.filePath,
          callsMade: outDegree.get(nodeId) || 0,
          callsReceived: inDegree.get(nodeId) || 0,
          isCallSite: true,
          pendingFwd: 0,
          pendingBwd: 0,
          expandedFwdCount: 0,
          expandedBwdCount: 0,
          onNavigate,
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
        fileId: astNode.fileId,
        filePath: astNode.filePath,
        callsMade: outDegree.get(nodeId) || 0,
        callsReceived: inDegree.get(nodeId) || 0,
        pendingFwd: 0,
        pendingBwd: 0,
        expandedFwdCount: 0,
        expandedBwdCount: 0,
        onNavigate,
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

  return { nodes: graphNodes, edges: graphEdges, externalCalleesByCaller, externalCallersByCallee, astNodeMap: nodeMap };
}

/** 图例下拉按钮 */
function LegendDropdown({ edgeCounts }: { edgeCounts: Record<string, number> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors px-2 py-1 rounded-md hover:bg-[var(--bg-hover)]"
      >
        <span>图例</span>
        <span className="text-[9px]">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-50 bg-[var(--bg-card)] rounded-lg shadow-xl border border-[var(--border)] p-4 min-w-[280px]">
            <div className="space-y-3">
              <div>
                <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">节点类型</p>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                  {Object.entries(NODE_TYPE_CONFIG).map(([type, config]) => (
                    <span key={type} className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                      <span className="w-2.5 h-2.5 rounded flex-shrink-0" style={{ backgroundColor: config.color }} />
                      <span>{config.label}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">调用类型</p>
                <div className="space-y-1">
                  {["static", "dynamic", "unknown"].map((type) => (
                    <span key={type} className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
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
                <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">交互说明</p>
                <div className="space-y-1">
                  <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "var(--color-brand)", color: "#fff", width: 16, height: 16 }}>▼N</span>
                    <span>品牌色 ▼N：N 个外部调用可展开</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "var(--color-status-error)", color: "#fff", width: 16, height: 16 }}>▼N</span>
                    <span>红色 ▼N：已展开 N 个，点击折叠</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "var(--color-brand)", color: "#fff", width: 16, height: 16 }}>▲N</span>
                    <span>品牌色 ▲N：N 个外部调用者可展开</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                    <span className="inline-flex items-center justify-center rounded-full text-[8px] font-bold flex-shrink-0" style={{ backgroundColor: "var(--color-status-error)", color: "#fff", width: 16, height: 16 }}>▲N</span>
                    <span>红色 ▲N：已展开 N 个，点击折叠</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
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

export function CallGraph({ fileId, repositoryId, onNavigate, highlightNodeId }: CallGraphProps) {
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
   * - pendingBwdByNode: 每个节点的待展开外部 caller 队列（API 获取）
   * - externalCallerNodes: API 获取的外部 caller 节点数据
   * - externalCallerEdges: API 获取的外部 caller 边
   * - externalCallersLoadedSet: 已通过 API 获取外部 caller 的节点集合
   */
  const [expandedFwdByNode, setExpandedFwdByNode] = useState<Map<string, Set<string>>>(new Map());
  const [expandedBwdByNode, setExpandedBwdByNode] = useState<Map<string, Set<string>>>(new Map());
  const [exitingNodeIds, setExitingNodeIds] = useState<Set<string>>(new Set());
  const [bwdLoadingSet, setBwdLoadingSet] = useState<Set<string>>(new Set());
  const [pendingBwdByNode, setPendingBwdByNode] = useState<Map<string, string[]>>(new Map());
  // Nodes that have already been API-checked for bwd (regardless of result)
  const bwdCheckedSetRef = useRef<Set<string>>(new Set());
  const pendingFwdByNodeRef = useRef<Map<string, string[]>>(new Map());
  // 预计算的外部 caller 索引（来自现有边数据），用于立即给出向上展开计数
  const prebuiltBwdByNodeRef = useRef<Map<string, string[]>>(new Map());
  // API 获取的外部 caller 数据（用于实际展开节点渲染）
  const apiBwdByNodeRef = useRef<Map<string, string[]>>(new Map());
  const [externalCallerNodes, setExternalCallerNodes] = useState<Map<string, any>>(new Map());
  const [externalCallerEdges, setExternalCallerEdges] = useState<Map<string, Edge>>(new Map());
  const isMountedRef = useRef(true);
  const exitTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const graphDataRef = useRef<{
    nodes: Node[];
    edges: Edge[];
    externalCalleesByCaller: Map<string, string[]>;
    externalCallersByCallee: Map<string, string[]>;
    astNodeMap: Map<string, any>;
  } | null>(null);

  const reactFlowRef = useRef<any>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

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
      setPendingBwdByNode(new Map());
      pendingFwdByNodeRef.current = new Map();
      bwdCheckedSetRef.current = new Set();
      setExternalCallerNodes(new Map());
      setExternalCallerEdges(new Map());
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
      const result = await buildGraphData(deduped, callEdges, fileId, onNavigate);
      if (!cancelled && isMountedRef.current) {
        setGraphData(result);
        graphDataRef.current = result;
        // 初始化 pendingFwdByNode：每个 caller 的全部外部 callee 都视为待展开
        pendingFwdByNodeRef.current = new Map(result.externalCalleesByCaller);
        // 初始化预计算的外部 caller 索引：用于立即给出向上展开计数（无需等待 API）
        prebuiltBwdByNodeRef.current = new Map(result.externalCallersByCallee);
        apiBwdByNodeRef.current = new Map();
        setExpandedFwdByNode(new Map());
        setExpandedBwdByNode(new Map());
        // 初始化 pendingBwdByNode 同步设置为预计算值，使按钮立即显示实际计数
        setPendingBwdByNode(new Map(result.externalCallersByCallee));
        setExternalCallerNodes(new Map());
        setExternalCallerEdges(new Map());
        setGlobalError(null);
      }
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fileId, allAstNodes, callEdges, onNavigate]);

  useEffect(() => {
    if (highlightNodeId && graphData) {
      const exists = graphData.nodes.some((n) => n.id === highlightNodeId);
      if (exists) {
        setFocusedNodeId(highlightNodeId);
      }
    }
  }, [highlightNodeId, graphData]);

  // 预加载已移除：现在外部 caller 计数通过 buildGraphData 中预计算的 externalCallersByCallee 同步获取，无需 API 调用

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

  // 同步 displayedNodeCountRef 与最新 state，避免异步闭包过期值
  const displayedNodeCountRef = useRef(0);
  useEffect(() => {
    displayedNodeCountRef.current = displayedNodeCount;
  }, [displayedNodeCount]);

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
        const maxToAdd = Math.min(MAX_EXTERNAL_PER_EXPANSION, remaining.length);
        const spaceLeft = MAX_TOTAL_NODES - displayedNodeCountRef.current;
        const allowed = Math.min(maxToAdd, Math.max(0, spaceLeft));
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
  }, [expandedFwdByNode, collapseFwdRecursive, collectFwdDescendants, startExitAnimation]);

  /**
   * 向上展开/折叠 toggle（caller 方向，需 API 调用）
   *
   * pendingBwdByNode 语义：每个节点存储的是"尚未显示的外部 caller ID 列表"
   * （已展开的不在其中）。这样第二次点击时 remaining = pending.length 就是正确的增量。
   *
   * - 首次：调用 getCallers API 获取外部 caller，将未显示的存入 pendingBwdByNode
   * - 有 pending：批量展开最多 MAX_EXTERNAL_PER_EXPANSION 个外部 caller
   * - 已展开（无 pending）：折叠该节点的 bwd 子树（原路按步折叠，递归移除后代）
   */
  const toggleBwd = useCallback(async (nodeId: string) => {
    // === Collapse path: checked + nothing remaining to expand ===
    const bwdExpanded = expandedBwdByNode.get(nodeId) || new Set();
    const bwdPendingList = pendingBwdByNode.get(nodeId);
    const isChecked = bwdPendingList !== undefined;
    const hasRemaining = isChecked && bwdPendingList.length > 0;
    const shouldCollapse = isChecked && !hasRemaining && bwdExpanded.size > 0;

    if (shouldCollapse) {
      // 折叠前先标记为已检查，防止折叠后显示 "?"
      bwdCheckedSetRef.current.add(nodeId);
      // 收集所有 bwd 后代，播放退出动画，再真正移除
      const toRemove = collectBwdDescendants(expandedBwdByNode, nodeId);
      startExitAnimation(toRemove, () => {
        setExpandedBwdByNode((prev) => {
          const next = new Map(prev);
          collapseBwdRecursive(next, nodeId);
          return next;
        });
        // 移除 pendingBwdByNode 条目，让预计算索引重新填充计数
        setPendingBwdByNode((prev) => {
          const next = new Map(prev);
          next.delete(nodeId);
          return next;
        });
      });
      return;
    }

    // 标记当前节点为已检查（无论 API 结果如何），防止折叠后显示 "?"
    bwdCheckedSetRef.current.add(nodeId);

    setBwdLoadingSet((prev) => new Set(prev).add(nodeId));
    try {
      const { getCallers } = await import("@/api/call-edges");
      const callers = await getCallers(nodeId).catch((e) => {
        console.error("getCallers error:", e);
        return [];
      }) as any[];

      const currentFileAstNodeIds = new Set<string>();
      for (const n of (graphDataRef.current?.nodes || [])) {
        const d = n.data as any;
        if (d?.isCurrentFile || d?.isCallSite) currentFileAstNodeIds.add(n.id);
      }
      const externalCallers = callers.filter((item: any) => {
        const caller = item.caller;
        if (!caller) return false;
        return !currentFileAstNodeIds.has(caller.id);
      });

      const externalCallerIds = externalCallers.map((item: any) => item.caller?.id).filter(Boolean) as string[];

      // 标记已检查 + 将 fetched 的子节点也标记为已检查
      for (const itemId of externalCallerIds) {
        bwdCheckedSetRef.current.add(itemId);
      }

      // pendingBwdByNode 只存"尚未显示"的 caller（已展开的不在里面）
      const currentExpanded = expandedBwdByNode.get(nodeId) || new Set();
      const unshownCallers = externalCallerIds.filter(id => !currentExpanded.has(id));
      setPendingBwdByNode((prev) => {
        const next = new Map(prev);
        next.set(nodeId, unshownCallers);
        return next;
      });

      // 存储全部 API caller ID 列表（用于折叠后重新计算 pending 计数）
      apiBwdByNodeRef.current.set(nodeId, externalCallerIds);

      // 存入 externalCallerNodes 和 externalCallerEdges
      if (externalCallers.length > 0 && isMountedRef.current) {
        setExternalCallerNodes((prev) => {
          const next = new Map(prev);
          for (const item of externalCallers) {
            const caller = item.caller;
            if (caller) next.set(caller.id, caller);
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
                style: { stroke: style.stroke, strokeDasharray: style.strokeDasharray, strokeWidth: style.width },
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

        // 有外部 caller 时自动展开
        if (unshownCallers.length === 0) return;
        setExpandedBwdByNode((prev) => {
          const next = new Map(prev);
          const current = new Set(next.get(nodeId) || []);
          const maxToAdd = Math.min(MAX_EXTERNAL_PER_EXPANSION, unshownCallers.length);
          const spaceLeft = MAX_TOTAL_NODES - displayedNodeCountRef.current;
          if (spaceLeft <= 0) {
            setGlobalError(`已达节点数上限（${MAX_TOTAL_NODES}），请先折叠部分节点`);
            return prev;
          }
          const allowed = Math.min(maxToAdd, spaceLeft);
          for (let i = 0; i < allowed; i++) {
            current.add(unshownCallers[i]);
          }
          next.set(nodeId, current);
          return next;
        });
        setGlobalError(null);
      }
    } catch (e) {
      console.error("toggleBwd fetch error:", e);
      setGlobalError("获取外部调用者失败");
    } finally {
      if (isMountedRef.current) {
        setBwdLoadingSet((prev) => {
          const next = new Set(prev);
          next.delete(nodeId);
          return next;
        });
      }
    }
  }, [expandedBwdByNode, pendingBwdByNode, collapseBwdRecursive, collectBwdDescendants, startExitAnimation]);

  /**
   * 一次性展开所有剩余外部 caller（Shift+Click 或 toolbar 按钮）
   */
  const toggleBwdAll = useCallback(async (nodeId: string) => {
    setBwdLoadingSet((prev) => new Set(prev).add(nodeId));
    try {
      const { getCallers } = await import("@/api/call-edges");
      const callers = await getCallers(nodeId).catch((e) => {
        console.error("getCallers error:", e);
        return [];
      }) as any[];

      const currentFileAstNodeIds = new Set<string>();
      for (const n of (graphDataRef.current?.nodes || [])) {
        const d = n.data as any;
        if (d?.isCurrentFile || d?.isCallSite) currentFileAstNodeIds.add(n.id);
      }
      const externalCallers = callers.filter((item: any) => {
        const caller = item.caller;
        if (!caller) return false;
        return !currentFileAstNodeIds.has(caller.id);
      });

      const externalCallerIds = externalCallers.map((item: any) => item.caller?.id).filter(Boolean) as string[];

      // 标记已检查 + 子节点
      for (const itemId of externalCallerIds) {
        bwdCheckedSetRef.current.add(itemId);
      }

      // 将未显示的存入 pendingBwdByNode（语义：只存未显示的）
      const currentExpanded = expandedBwdByNode.get(nodeId) || new Set();
      const unshownCallers = externalCallerIds.filter(id => !currentExpanded.has(id));
      setPendingBwdByNode((prev) => {
        const next = new Map(prev);
        next.set(nodeId, unshownCallers);
        return next;
      });

      // 存储全部 API caller ID 列表
      apiBwdByNodeRef.current.set(nodeId, externalCallerIds);

      // 存入 externalCallerNodes/Edges
      if (externalCallers.length > 0 && isMountedRef.current) {
        setExternalCallerNodes((prev) => {
          const next = new Map(prev);
          for (const item of externalCallers) {
            const caller = item.caller;
            if (caller) next.set(caller.id, caller);
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
                style: { stroke: style.stroke, strokeDasharray: style.strokeDasharray, strokeWidth: style.width },
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

        // 一次性全部展开
        if (unshownCallers.length === 0) return;
        setExpandedBwdByNode((prev) => {
          const next = new Map(prev);
          const current = new Set(next.get(nodeId) || []);
          const spaceLeft = MAX_TOTAL_NODES - displayedNodeCountRef.current;
          if (spaceLeft <= 0) {
            setGlobalError(`已达节点数上限（${MAX_TOTAL_NODES}），请先折叠部分节点`);
            return prev;
          }
          const allowed = Math.min(unshownCallers.length, spaceLeft);
          for (let i = 0; i < allowed; i++) {
            current.add(unshownCallers[i]);
          }
          next.set(nodeId, current);
          return next;
        });
        setGlobalError(null);
      }
    } catch (e) {
      console.error("toggleBwdAll fetch error:", e);
      setGlobalError("获取外部调用者失败");
    } finally {
      if (isMountedRef.current) {
        setBwdLoadingSet((prev) => {
          const next = new Set(prev);
          next.delete(nodeId);
          return next;
        });
      }
    }
  }, [expandedBwdByNode]);

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
    const pendingBwdCountByNode = new Map<string, number>();
    const expandedFwdCountByNode = new Map<string, number>();
    const expandedBwdCountByNode = new Map<string, number>();

    for (const [callerId, allCallees] of pendingFwdByNodeRef.current) {
      const expanded = expandedFwdByNode.get(callerId) || new Set();
      const remaining = allCallees.filter(id => !expanded.has(id));
      pendingFwdByNode.set(callerId, remaining.length);
      expandedFwdCountByNode.set(callerId, expanded.size);
    }

    for (const [callerId, allCallers] of pendingBwdByNode) {
      // pendingBwdByNode 现在只存"尚未显示"的 caller，所以直接取长度
      pendingBwdCountByNode.set(callerId, allCallers.length);
      expandedBwdCountByNode.set(callerId, (expandedBwdByNode.get(callerId) || new Set()).size);
    }

    // 未通过 API 检查过的节点：用预计算的外部 caller 索引给出实际计数
    for (const [callerId, allCallers] of prebuiltBwdByNodeRef.current) {
      if (!pendingBwdCountByNode.has(callerId)) {
        const expanded = expandedBwdByNode.get(callerId) || new Set();
        const remaining = allCallers.filter(id => !expanded.has(id));
        pendingBwdCountByNode.set(callerId, remaining.length);
        expandedBwdCountByNode.set(callerId, expanded.size);
      }
    }

    // API 获取的外部 caller：用于折叠后重新计算 pending 计数
    for (const [callerId, allCallers] of apiBwdByNodeRef.current) {
      if (!pendingBwdCountByNode.has(callerId)) {
        const expanded = expandedBwdByNode.get(callerId) || new Set();
        const remaining = allCallers.filter(id => !expanded.has(id));
        pendingBwdCountByNode.set(callerId, remaining.length);
        expandedBwdCountByNode.set(callerId, expanded.size);
      }
    }

    // 聚焦模式：只显示聚焦节点 + 直接邻居，但仍需注入 pending/expanded 计数
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

      // 注入 pending/expanded 计数到聚焦模式节点
      const hydratedNodes = filteredNodes.map((node) => {
        const pendingFwd = pendingFwdByNode.get(node.id) || 0;
        const pendingBwd = pendingBwdCountByNode.get(node.id) || 0;
        const expandedFwdCount = expandedFwdCountByNode.get(node.id) || 0;
        const expandedBwdCount = expandedBwdCountByNode.get(node.id) || 0;
        const bwdLoading = bwdLoadingSet.has(node.id);
        const bwdChecked = bwdCheckedSetRef.current.has(node.id);
        const hasPotentialExternal = prebuiltBwdByNodeRef.current.has(node.id);
        const isExiting = exitingNodeIds.has(node.id);
        return {
          ...node,
          data: {
            ...node.data,
            pendingFwd,
            pendingBwd,
            expandedFwdCount,
            expandedBwdCount,
            bwdLoading,
            bwdChecked,
            hasPotentialExternal,
            isExiting,
            isFocusedMode: true,
            onToggleFwd: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleFwd(node.id);
            },
            onToggleBwd: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleBwd(node.id);
            },
            onToggleBwdAll: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleBwdAll(node.id);
            },
            totalAvailableBwd: prebuiltBwdByNodeRef.current.get(node.id)?.length || 0,
          },
        };
      });
      return { nodes: hydratedNodes, edges: filteredEdges };
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
        const pendingBwd = pendingBwdCountByNode.get(node.id) || 0;
        const expandedFwdCount = expandedFwdCountByNode.get(node.id) || 0;
        const expandedBwdCount = expandedBwdCountByNode.get(node.id) || 0;
        const bwdLoading = bwdLoadingSet.has(node.id);
        const bwdChecked = bwdCheckedSetRef.current.has(node.id);
        const hasPotentialExternal = prebuiltBwdByNodeRef.current.has(node.id);
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
            bwdLoading,
            bwdChecked,
            hasPotentialExternal,
            isExiting,
            onToggleFwd: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleFwd(node.id);
            },
            onToggleBwd: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleBwd(node.id);
            },
            onToggleBwdAll: (e: React.MouseEvent) => {
              e.stopPropagation();
              toggleBwdAll(node.id);
            },
            totalAvailableBwd: prebuiltBwdByNodeRef.current.get(node.id)?.length || 0,
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

    // 2. 外部 caller 节点（排除已在 graphData 中的节点，避免重复 key）
    const graphDataNodeIds = new Set(graphData.nodes.map((n) => n.id));
    for (const id of externalCallerNodeIds) {
      if (visibleNodeIds.has(id) && !graphDataNodeIds.has(id)) {
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
              fileId: callerData.file_id || callerData.id,
              filePath: callerData.file_path,
              callsMade: 0,
              callsReceived: 0,
              pendingFwd: pendingFwdByNode.get(id) || 0,
              pendingBwd: pendingBwdCountByNode.get(id) || 0,
              expandedFwdCount: expandedFwdCountByNode.get(id) || 0,
              expandedBwdCount: expandedBwdCountByNode.get(id) || 0,
              bwdLoading: bwdLoadingSet.has(id),
              bwdChecked: bwdCheckedSetRef.current.has(id),
              hasPotentialExternal: prebuiltBwdByNodeRef.current.has(id),
              isExiting,
              onToggleFwd: (e: React.MouseEvent) => {
                e.stopPropagation();
                toggleFwd(id);
              },
              onToggleBwd: (e: React.MouseEvent) => {
                e.stopPropagation();
                toggleBwd(id);
              },
              onToggleBwdAll: (e: React.MouseEvent) => {
                e.stopPropagation();
                toggleBwdAll(id);
              },
              totalAvailableBwd: prebuiltBwdByNodeRef.current.get(id)?.length || 0,
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
  }, [graphData, focusedNodeId, expandedFwdByNode, expandedBwdByNode, exitingNodeIds, externalCallerNodes, externalCallerEdges, toggleFwd, toggleBwd, toggleBwdAll, bwdLoadingSet, pendingBwdByNode]);

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
    for (const allCallers of pendingBwdByNode.values()) {
      // pendingBwdByNode 现在只存未显示的 caller，直接累加长度
      sum += allCallers.length;
    }
    return sum;
  }, [expandedFwdByNode, pendingBwdByNode]);

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

  // 当前文件节点列表（用于侧边栏快速定位导航）
  const currentFileNodeList = useMemo(() => {
    return displayedNodes.filter((node) => {
      const d = node.data as any;
      return d?.isCurrentFile || d?.isCallSite;
    }).map((node) => ({
      id: node.id,
      label: (node.data as any)?.label || "",
      nodeType: (node.data as any)?.nodeType || "",
      nodeTypeLabel: (node.data as any)?.nodeTypeLabel || "",
      icon: (node.data as any)?.icon || "",
    }));
  }, [displayedNodes]);

  const handleNodeLocate = useCallback((nodeId: string) => {
    if (reactFlowRef.current) {
      reactFlowRef.current.setCenter(
        displayedNodes.find(n => n.id === nodeId)?.position.x || 0,
        displayedNodes.find(n => n.id === nodeId)?.position.y || 0,
        { zoom: 1.5, duration: 500 }
      );
    }
  }, [displayedNodes]);

  return (
    <div className="h-full flex flex-col">
      {isLoading ? (
        <div className="h-full flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-4 border-brand border-t-transparent rounded-full animate-spin mx-auto mb-3" />
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
          <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border)] bg-[var(--bg-card)]/50 backdrop-blur flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              {focusedNodeId ? (
                <>
                  <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">聚焦模式</span>
                  <button
                    onClick={() => setSelectedNodeForChain(focusedNodeId)}
                    className="text-xs px-2 py-1 rounded-md bg-brand/10 text-brand hover:bg-brand/20 transition-colors font-medium whitespace-nowrap"
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
                      className="text-xs px-2 py-0.5 rounded-md bg-[var(--bg-hover)] text-[var(--text-secondary)] hover:bg-[var(--bg-card)] transition-colors font-medium whitespace-nowrap"
                    >
                      收起全部 ({totalExpanded})
                    </button>
                  )}
                  {totalPending > 0 && (
                    <span className="text-xs text-brand whitespace-nowrap">
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
            <div className="px-4 py-2 bg-status-warning/10 border-b border-status-warning/30 text-xs text-status-warning flex items-center justify-between">
              <span>⚠ {globalError}</span>
              <button
                onClick={() => setGlobalError(null)}
                className="text-status-warning hover:text-status-error ml-2"
              >✕</button>
            </div>
          )}

          {/* ReactFlow 图 */}
          <div className="flex-1 flex relative">
            {/* 悬浮球快速定位导航 */}
            {currentFileNodeList.length > 0 && (
              <>
                <div className="absolute left-3 top-3 z-50">
                  <button
                    onClick={() => setSidebarOpen(!sidebarOpen)}
                    className="flex items-center justify-center w-8 h-8 rounded-full bg-[var(--bg-card)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] shadow-lg transition-all duration-200 cursor-pointer hover:scale-110"
                    title={sidebarOpen ? "收起节点列表" : "展开节点列表"}
                  >
                    <span className="text-xs font-bold leading-none">
                      {sidebarOpen ? "✕" : currentFileNodeList.length}
                    </span>
                  </button>
                  {sidebarOpen && (
                    <>
                      {/* 点击外部关闭 */}
                      <div className="fixed inset-0 z-40" onClick={() => setSidebarOpen(false)} />
                      <div className="absolute left-10 top-0 z-50 w-52 max-h-[60vh] bg-[var(--bg-card)] border border-[var(--border)] rounded-xl shadow-2xl overflow-hidden">
                        <div className="px-3 py-2 text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider border-b border-[var(--border)] flex items-center justify-between bg-[var(--bg-hover)]">
                          <span>本文件节点</span>
                          <span className="text-[9px] font-normal normal-case">{currentFileNodeList.length}</span>
                        </div>
                        <div className="overflow-y-auto max-h-[calc(60vh-32px)] py-1">
                          {currentFileNodeList.map((node) => {
                            const config = NODE_TYPE_CONFIG[node.nodeType];
                            return (
                              <button
                                key={node.id}
                                onClick={() => {
                                  handleNodeLocate(node.id);
                                  setSidebarOpen(false);
                                }}
                                className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors"
                                title={`定位到 ${node.label}`}
                              >
                                <span
                                  className="w-2 h-2 rounded-full flex-shrink-0"
                                  style={{ backgroundColor: config?.color || "#6b7280" }}
                                />
                                <span className="truncate">{node.label}</span>
                                {config?.icon && (
                                  <span className="text-[9px] opacity-50 flex-shrink-0 ml-auto">{config.icon}</span>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </>
            )}
            <ReactFlowProvider>
              <ReactFlow
                nodes={displayedNodes}
                edges={finalEdges}
                nodeTypes={nodeTypes}
                onNodeClick={onNodeClick}
                onNodeContextMenu={onNodeContextMenu}
                onPaneClick={onPaneClick}
                onEdgeMouseEnter={onEdgeMouseEnter}
                onEdgeMouseLeave={onEdgeMouseLeave}
                onInit={(instance) => { reactFlowRef.current = instance; }}
                fitView
                minZoom={0.1}
                maxZoom={3}
                defaultViewport={{ x: 0, y: 0, zoom: 0.65 }}
              >
                <Background color="var(--border)" gap={16} />
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
            </ReactFlowProvider>
          </div>

          {/* 调用链面板 Modal */}
          {selectedNodeForChain && chainNodeData && (
            <CallChainPanel
              nodeId={chainNodeData.id}
              nodeName={chainNodeData.name}
              nodeType={chainNodeData.nodeType}
              filePath={chainNodeData.filePath}
              onClose={() => setSelectedNodeForChain(null)}
              onNavigate={onNavigate}
            />
          )}
        </>
      )}
    </div>
  );
}
