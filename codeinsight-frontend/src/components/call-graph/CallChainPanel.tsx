/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

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

const CALL_TYPE_COLORS: Record<string, string> = {
  static: "60a5fa", dynamic: "fbbf24", unknown: "9ca3af",
};

const NODE_W = 140;
const NODE_H = 56;
const LAYER_SPACING = 140;
const NODE_SPACING = 80;

interface CallChainPanelProps {
  nodeId: string; nodeName: string; nodeType: string;
  filePath?: string; onClose: () => void;
}

function shortFilePath(fp: string, maxLen = 24): string {
  if (!fp || fp.length <= maxLen) return fp || "";
  const parts = fp.split(/[/\\]/);
  let r = parts[parts.length - 1];
  for (let i = parts.length - 2; i >= 0; i--) {
    const c = `${parts[i]}/${r}`;
    if (c.length > maxLen) break;
    r = c;
  }
  return `…${r.startsWith("/") || r.startsWith("\\") ? "" : "/"}${r}`;
}

/* 节点元数据 */
interface RawNode {
  id: string; name: string; nodeType: string; filePath?: string;
  callName: string; callType: string; depth: number;
  parentId: string | null;
  loadedFwd: boolean; loadedBwd: boolean;
  loading: boolean;
}

/* 按 depth 分层计算 position */
function computePositions(defs: { id: string; depth: number }[]) {
  const depthMap = new Map<number, string[]>();
  for (const d of defs) {
    if (!depthMap.has(d.depth)) depthMap.set(d.depth, []);
    depthMap.get(d.depth)!.push(d.id);
  }
  const depths = [...depthMap.keys()].sort((a, b) => a - b);
  const posMap = new Map<string, { x: number; y: number }>();
  for (const depth of depths) {
    const ids = depthMap.get(depth)!;
    const y = depth * LAYER_SPACING;
    const w = Math.max(ids.length * (NODE_W + NODE_SPACING), NODE_W);
    const sx = -w / 2 + NODE_W / 2;
    for (let i = 0; i < ids.length; i++) posMap.set(ids[i], { x: sx + i * (NODE_W + NODE_SPACING), y });
  }
  return posMap;
}

function makeRfNode(r: RawNode, isRoot: boolean, pos: { x: number; y: number }): Node {
  return {
    id: r.id, type: "chainNode", position: pos,
    data: {
      label: r.name, nodeType: r.nodeType, filePath: r.filePath,
      callName: r.callName, callType: r.callType, depth: r.depth,
      isRoot, loaded: r.loadedFwd && r.loadedBwd, loading: r.loading,
    },
  };
}

const nodeTypes = { chainNode: ChainNodeComponent };
const edgeTypes = { chainEdge: ChainEdgeComponent };
const defaultEdgeOptions = { type: "smoothstep" };

/* ============ 主面板 ============ */
export function CallChainPanel({ nodeId, nodeName, nodeType, filePath, onClose }: CallChainPanelProps) {
  const [rfNodes, setRfNodes] = useState<Map<string, Node>>(new Map());
  const [rfEdges, setRfEdges] = useState<Map<string, Edge>>(new Map());
  const [rfInstance, setRfInstance] = useState<any>(null);
  const rawRef = useRef(new Map<string, RawNode>());

  // 初始化
  useEffect(() => {
    const rootRaw: RawNode = {
      id: nodeId, name: nodeName, nodeType, filePath,
      callName: "", callType: "", depth: 0, parentId: null,
      loadedFwd: false, loadedBwd: false, loading: false,
    };
    rawRef.current = new Map([[nodeId, rootRaw]]);
    const pos = computePositions([rootRaw]).get(nodeId)!;
    setRfNodes(new Map([[nodeId, makeRfNode(rootRaw, true, pos)]]));
    setRfEdges(new Map());
    setTimeout(() => loadChildren(nodeId), 50);
  }, [nodeId, nodeName, nodeType, filePath]);

  // 更新 rawRef + 同步 RF 节点
  const syncNode = useCallback((id: string, patch: Partial<RawNode> & { loading?: boolean }) => {
    const raw = rawRef.current.get(id);
    if (!raw) return;
    const updated = { ...raw, ...patch };
    rawRef.current.set(id, updated);

    setRfNodes((prev) => {
      const n = prev.get(id);
      if (!n) return prev;
      const next = new Map(prev);
      next.set(id, {
        ...n,
        data: {
          ...n.data,
          loaded: updated.loadedFwd && updated.loadedBwd,
          loading: updated.loading ?? false,
        },
      });
      return next;
    });
  }, []);

  // 加载某节点的双向调用
  const loadChildren = useCallback(async (parentId: string) => {
    const raw = rawRef.current.get(parentId);
    if (!raw || raw.loading || (raw.loadedFwd && raw.loadedBwd)) return;

    syncNode(parentId, { loading: true });

    try {
      const { getCallees, getCallers } = await import("@/api/call-edges");
      const [callees, callers] = await Promise.all([
        getCallees(parentId).catch(() => []),
        getCallers(parentId).catch(() => []),
      ]);

      const newRaws: RawNode[] = [];
      const newEdges: Edge[] = [];
      const nowRaws = rawRef.current;

      const process = (items: any[], dir: "forward" | "backward") => {
        for (const item of items) {
          const calleeOrCaller = dir === "forward" ? item.callee : item.caller;
          const childId = calleeOrCaller?.id || `${parentId}-${item.call_name || "ext"}-${dir}`;
          const childDepth = dir === "forward" ? raw.depth + 1 : raw.depth - 1;
          const isExternal = !calleeOrCaller;

          if (!nowRaws.has(childId)) {
            const nr: RawNode = {
              id: childId,
              name: calleeOrCaller?.name || item.call_name || "(未知)",
              nodeType: calleeOrCaller?.node_type || "call",
              filePath: calleeOrCaller?.file_path,
              callName: item.call_name,
              callType: item.call_type || "unknown",
              depth: childDepth,
              parentId,
              loadedFwd: isExternal,    // 外部节点无需再展开
              loadedBwd: isExternal,
              loading: false,
            };
            newRaws.push(nr);
            nowRaws.set(childId, nr);
          }

          newEdges.push({
            id: `${parentId}-${childId}-${dir}`,
            source: dir === "forward" ? parentId : childId,
            target: dir === "forward" ? childId : parentId,
            label: item.call_name || "",
            data: { callType: item.call_type || "unknown" },
          });
        }
      };

      process(callees, "forward");
      process(callers, "backward");

      // 重新计算所有节点位置
      const allDefs = Array.from(nowRaws.values()).map((r) => ({ id: r.id, depth: r.depth }));
      const posMap = computePositions(allDefs);

      // 标记父节点双向已加载
      syncNode(parentId, { loadedFwd: true, loadedBwd: true, loading: false });

      // 批量更新 RF 节点
      setRfNodes((prev) => {
        const next = new Map(prev);
        // 更新父节点位置
        const parentRf = next.get(parentId);
        if (parentRf) {
          next.set(parentId, {
            ...parentRf,
            position: posMap.get(parentId) || parentRf.position,
            data: { ...parentRf.data, loaded: true, loading: false },
          });
        }
        // 添加新节点 + 更新所有节点位置
        for (const nr of newRaws) {
          next.set(nr.id, makeRfNode(nr, false, posMap.get(nr.id) || { x: 0, y: 0 }));
        }
        for (const [id, oldNode] of next) {
          const pos = posMap.get(id);
          if (pos) next.set(id, { ...oldNode, position: pos });
        }
        return next;
      });

      // 更新边
      if (newEdges.length > 0) {
        setRfEdges((prev) => {
          const next = new Map(prev);
          for (const e of newEdges) next.set(e.id, e);
          return next;
        });
      }

      setTimeout(() => (rfInstance as any)?.fitView?.({ duration: 200, padding: 0.15 }), 150);

    } catch (error) {
      console.error("loadChildren error:", error);
      syncNode(parentId, { loading: false });
    }
  }, [rfInstance, syncNode]);

  const handleNodeClick = useCallback((_event: any, node: any) => {
    const raw = rawRef.current.get(node.id);
    if (!raw) return;
    const bothLoaded = raw.loadedFwd && raw.loadedBwd;
    if (!bothLoaded && !raw.loading) {
      loadChildren(node.id);
    }
  }, [loadChildren]);

  const nodes = useMemo(() => [...rfNodes.values()], [rfNodes]);
  const edges = useMemo(() => [...rfEdges.values()], [rfEdges]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        className="relative bg-white rounded-xl shadow-2xl flex flex-col overflow-hidden"
        style={{ width: 960, maxWidth: "95vw", height: "85vh", minHeight: "60vh" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部栏 */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3">
              <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: NODE_TYPE_CONFIG[nodeType]?.color || "#6b7280" }} />
              <h3 className="text-base font-semibold text-gray-900 truncate">{nodeName}</h3>
              <span className="text-xs text-gray-400">{NODE_TYPE_CONFIG[nodeType]?.label || nodeType}</span>
            </div>
            {filePath && <p className="mt-1 text-xs text-gray-400 truncate ml-6">{shortFilePath(filePath)}</p>}
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 ml-4 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors text-sm"
          >✕</button>
        </div>

        {/* React Flow 画布 */}
        <div className="flex-1 overflow-hidden" style={{ position: "relative", minHeight: 0 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            onNodeClick={handleNodeClick}
            onInit={setRfInstance}
            fitView
            minZoom={0.2}
            maxZoom={2}
            style={{ width: "100%", height: "100%" }}
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>

        {/* 底部栏 */}
        <div className="px-6 py-3 border-t border-gray-100 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-4 text-xs text-gray-400">
            {Object.entries(CALL_TYPE_COLORS).map(([k, v]) => (
              <span key={k} className="flex items-center gap-1">
                <span className="w-3 h-0.5 inline-block" style={{ backgroundColor: `#${v}`, borderTop: k === "dynamic" ? "2px dashed" : undefined }} />
                <span>{k}</span>
              </span>
            ))}
            <span className="text-gray-300">|</span>
            <span>节点: {nodes.length}</span>
            <span>边: {edges.length}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============ 节点组件 ============ */
function ChainNodeComponent({ data }: any) {
  const cfg = NODE_TYPE_CONFIG[data.nodeType] || NODE_TYPE_CONFIG.call;
  const isRoot = data.isRoot;

  return (
    <div
      className="relative flex flex-col items-center justify-center cursor-pointer select-none rounded-lg"
      style={{
        width: NODE_W, height: NODE_H,
        backgroundColor: isRoot ? `${cfg.color}20` : "rgba(243, 244, 246, 0.85)",
        border: `2px solid ${isRoot ? cfg.borderColor : "#d1d5db"}`,
      }}
    >
      {data.loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/5 rounded-lg z-10">
          <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      <span className="text-xs font-bold" style={{ color: cfg.color }}>{cfg.icon}</span>
      <span className="text-sm font-medium text-gray-800 truncate w-full px-2 text-center leading-tight">{data.label}</span>
      {data.filePath && (
        <span className="text-[10px] text-gray-400 truncate w-full px-2 text-center leading-tight">{shortFilePath(data.filePath)}</span>
      )}

      <Handle id="source" type="source" position={Position.Bottom} style={{ background: cfg.color }} />
      <Handle id="target" type="target" position={Position.Top} style={{ background: cfg.color }} />
    </div>
  );
}

/* ============ 边组件（hover tooltip） ============ */
function ChainEdgeComponent({ sourceX, sourceY, targetX, targetY, label, data, style }: any) {
  const color = CALL_TYPE_COLORS[data?.callType] || "9ca3af";
  const isDynamic = data?.callType === "dynamic";

  return (
    <>
      <path
        d={`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`}
        fill="none" stroke={`#${color}`}
        strokeWidth={2} strokeDasharray={isDynamic ? "5,5" : "0"}
        style={style}
      />
      {label && (
        <g>
          {/* 背景透明矩形，hover 区域 */}
          <rect
            x={(sourceX + targetX) / 2 - 50}
            y={(sourceY + targetY) / 2 - 16}
            width={100} height={32} rx={6}
            fill="transparent"
            className="cursor-pointer"
          >
            <title>{label}</title>
          </rect>
          {/* 调用名标签，hover 时显示 */}
          <text
            x={(sourceX + targetX) / 2}
            y={(sourceY + targetY) / 2 + 12}
            textAnchor="middle"
            fill="transparent"
            className="hover-edge-label"
            style={{ fontSize: 0 }}
          >
            <title>{label}</title>
          </text>
        </g>
      )}
    </>
  );
}