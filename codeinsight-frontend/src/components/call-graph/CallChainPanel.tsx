/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useState, useCallback, useEffect, useMemo, useRef, type MouseEvent as ReactMouseEvent } from "react";
import { motion } from "framer-motion";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import Elk from "elkjs";
import "@xyflow/react/dist/style.css";

const ELKConstructor = Elk;

const NODE_ENTER_DURATION = 0.28;
const NODE_EXIT_DURATION = 0.22;
const NODE_POSITION_TRANSITION = 350;

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
  static: "60a5fa",
  dynamic: "fbbf24",
  unknown: "9ca3af",
};

const NODE_W = 140;
const NODE_H = 56;
/** 每次展开节点的子节点上限 */
const MAX_NODES_PER_EXPANSION = 8;
/** 整张图的总节点数上限，防止无限展开导致性能问题 */
const MAX_TOTAL_NODES = 80;
/** 每次点击 "+N" 徽章追加加载的节点数 */
const LOAD_MORE_BATCH = 5;

const elk = new ELKConstructor({
  defaultLayoutOptions: {
    "elk.algorithms.layered": "true",
    "elk.layered.spacing.nodeNodeBetweenLayers": "65",
    "elk.layered.spacing.nodeNodeWithinLayers": "25",
    "elk.layered.spacing.edgeNodeBetweenLayers": "15",
    "elk.spacing.nodeNode": "15",
    "elk.direction": "DOWN",
    "elk.unflatten": "true",
    "elk.layered.unflatten.maxDegree": "1",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
    "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED",
    "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH",
    "elk.aspectRatio": "1.4",
    "elk.padding": "[top=20,left=20,bottom=20,right=20]",
  },
});

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
  /** 该节点尚未展开到图中的子节点数（出度方向） */
  pendingFwd?: number;
  /** 该节点尚未展开到图中的父节点数（入度方向） */
  pendingBwd?: number;
  /** 加载错误信息 */
  error?: string;
}

function makeRfNode(r: RawNode, isRoot: boolean, pos: { x: number; y: number }): Node {
  return {
    id: r.id, type: "chainNode", position: pos,
    style: {
      transition: `transform ${NODE_POSITION_TRANSITION}ms cubic-bezier(0.22, 1, 0.36, 1)`,
    },
    data: {
      label: r.name, nodeType: r.nodeType, filePath: r.filePath,
      callName: r.callName, callType: r.callType, depth: r.depth,
      isRoot, loaded: r.loadedFwd && r.loadedBwd, loading: r.loading,
      pendingFwd: r.pendingFwd || 0,
      pendingBwd: r.pendingBwd || 0,
      error: r.error,
      isExiting: false,
    },
  };
}

/* 节点组件前置声明 */
function ChainNodeComponent({ data, selected }: any) {
  const cfg = NODE_TYPE_CONFIG[data.nodeType] || NODE_TYPE_CONFIG.call;
  const isRoot = data.isRoot;
  const hasPending = (data.pendingFwd || 0) + (data.pendingBwd || 0) > 0;
  const totalPending = (data.pendingFwd || 0) + (data.pendingBwd || 0);
  const hasError = !!data.error;
  const isExiting = data.isExiting;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85, y: -8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.85, y: -8 }}
      transition={{
        duration: isExiting ? NODE_EXIT_DURATION : NODE_ENTER_DURATION,
        ease: "easeOut",
      }}
      className="relative flex flex-col items-center justify-center cursor-pointer select-none rounded-lg"
      style={{
        width: NODE_W, height: NODE_H,
        backgroundColor: isRoot ? `${cfg.color}20` : "rgba(243, 244, 246, 0.85)",
        border: `2px solid ${selected ? "#3b82f6" : (hasError ? "#ef4444" : isRoot ? cfg.borderColor : "#d1d5db")}`,
        boxShadow: selected ? "0 0 0 2px rgba(59, 130, 246, 0.3)" : "none",
      }}
      title={hasError ? data.error : `${cfg.label}：${data.label}`}
    >
      {data.loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/5 rounded-lg z-10">
          <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* 待展开计数指示器：可点击加载更多 */}
      {hasPending && !data.loading && (
        <div
          className="absolute -top-1 -right-1 flex items-center justify-center rounded-full text-[9px] font-bold px-1.5 py-0.5 cursor-pointer hover:scale-110 transition-transform z-20"
          style={{
            backgroundColor: hasError ? "#ef4444" : "#3b82f6",
            color: "#ffffff",
          }}
          title={hasError
            ? `加载失败：${data.error}，点击重试`
            : `还有 ${totalPending} 个调用未展开，点击加载更多（每次 ${LOAD_MORE_BATCH} 个）`}
        >
          +{totalPending}
        </div>
      )}

      <span className="text-xs font-bold" style={{ color: cfg.color }}>{cfg.icon}</span>
      <span className="text-sm font-medium text-gray-800 truncate w-full px-2 text-center leading-tight">{data.label}</span>
      {data.filePath && (
        <span className="text-[10px] text-gray-400 truncate w-full px-2 text-center leading-tight">{shortFilePath(data.filePath)}</span>
      )}

      <Handle id="source" type="source" position={Position.Bottom} style={{ background: cfg.color }} />
      <Handle id="target" type="target" position={Position.Top} style={{ background: cfg.color }} />
    </motion.div>
  );
}

/* 边组件：默认显示调用名（淡色），hover 时高亮 */
function ChainEdgeComponent({ sourceX, sourceY, targetX, targetY, label, data, style }: any) {
  const color = CALL_TYPE_COLORS[data?.callType] || "9ca3af";
  const isDynamic = data?.callType === "dynamic";
  const [hovered, setHovered] = useState(false);
  const midX = (sourceX + targetX) / 2;
  const midY = (sourceY + targetY) / 2;

  return (
    <>
      {/* 宽透明 path 作为 hover 区域 */}
      <path
        d={`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`}
        fill="none"
        stroke="transparent"
        strokeWidth={16}
        style={{ cursor: "pointer" }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      <path
        d={`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`}
        fill="none" stroke={`#${color}`}
        strokeWidth={hovered ? 3 : 2}
        strokeDasharray={isDynamic ? "5,5" : "0"}
        style={style}
        pointerEvents="none"
      />
      {label && (
        <g pointerEvents="none">
          <rect
            x={midX - 40}
            y={midY - 9}
            width={80} height={18} rx={4}
            fill={hovered ? "#1f2937" : "rgba(255,255,255,0.85)"}
            stroke={`#${color}`}
            strokeWidth={0.5}
            opacity={hovered ? 1 : 0.75}
          />
          <text
            x={midX}
            y={midY + 4}
            textAnchor="middle"
            fill={hovered ? "#ffffff" : "#374151"}
            style={{ fontSize: 10, fontWeight: 600 }}
          >
            {label.length > 12 ? `${label.slice(0, 11)}…` : label}
          </text>
        </g>
      )}
    </>
  );
}

const nodeTypes = { chainNode: ChainNodeComponent };
const edgeTypes = { chainEdge: ChainEdgeComponent };
const defaultEdgeOptions = { type: "smoothstep" };

/* ============ 主面板 ============ */
export function CallChainPanel({ nodeId, nodeName, nodeType, filePath, onClose }: CallChainPanelProps) {
  const [rfNodes, setRfNodes] = useState<Map<string, Node>>(new Map());
  const [rfEdgesState, setRfEdgesState] = useState<Map<string, Edge>>(new Map());
  const [rfInstance, setRfInstance] = useState<any>(null);
  /** 全局错误提示（如达到节点数上限） */
  const [globalError, setGlobalError] = useState<string | null>(null);
  const rawRef = useRef(new Map<string, RawNode>());
  const rfEdges = useRef(new Map<string, Edge>());
  /** 已卸载标志，防止 setState on unmounted */
  const isMountedRef = useRef(true);
  /** 待加载队列：每个 parent 节点的未展开项 */
  const pendingRef = useRef<Map<string, { fwd: any[]; bwd: any[] }>>(new Map());
  const exitTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  // 初始化
  useEffect(() => {
    const rootRaw: RawNode = {
      id: nodeId, name: nodeName, nodeType, filePath,
      callName: "", callType: "", depth: 0, parentId: null,
      loadedFwd: false, loadedBwd: false, loading: false,
    };
    rawRef.current = new Map([[nodeId, rootRaw]]);
    rfEdges.current = new Map();
    pendingRef.current = new Map();
    setGlobalError(null);
    setRfNodes(new Map([[nodeId, makeRfNode(rootRaw, true, { x: 0, y: 0 })]]));
    setRfEdgesState(new Map());
    setTimeout(() => loadChildren(nodeId), 50);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeId, nodeName, nodeType, filePath]);

  // 更新 rawRef + 同步 RF 节点（关键修复：任何字段变更都必须通过 syncNode 触发 UI 更新）
  const syncNode = useCallback((id: string, patch: Partial<RawNode> & { isExiting?: boolean }) => {
    const raw = rawRef.current.get(id);
    if (!raw) return;
    const updated = { ...raw, ...patch };
    rawRef.current.set(id, updated);

    if (!isMountedRef.current) return;

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
          pendingFwd: updated.pendingFwd || 0,
          pendingBwd: updated.pendingBwd || 0,
          error: updated.error,
          isExiting: patch.isExiting ?? n.data?.isExiting ?? false,
        },
      });
      return next;
    });
  }, []);

  // 使用 ELK 布局计算所有节点位置
  const computeLayout = useCallback(async (): Promise<Map<string, { x: number; y: number }>> => {
    const nowRaws = rawRef.current;
    const nowEdges = rfEdges.current;

    const elkNodes: Array<{ id: string; width: number; height: number }> = [];
    const elkEdges: Array<{ id: string; sources: string[]; targets: string[] }> = [];

    for (const r of nowRaws.values()) {
      elkNodes.push({ id: r.id, width: NODE_W, height: NODE_H });
    }

    for (const e of nowEdges.values()) {
      elkEdges.push({ id: e.id, sources: [e.source], targets: [e.target] });
    }

    const layoutGraph = await elk.layout({
      id: "chain-root", layoutOptions: {},
      children: elkNodes, edges: elkEdges,
    });

    const posMap = new Map<string, { x: number; y: number }>();
    for (const child of layoutGraph.children || []) {
      posMap.set(child.id as string, { x: Number(child.x) || 0, y: Number(child.y) || 0 });
    }

    return posMap;
  }, []);

  /**
   * 加载某节点的双向调用。
   * 修复点：
   * - 严格区分"已完整加载"和"部分加载（达到 MAX_NODES_PER_EXPANSION 后截断）"两种状态
   * - 截断时把剩余项存入 pendingRef，并 syncNode 触发 +N 徽章 UI 更新
   * - 达到 MAX_TOTAL_NODES 上限时停止加载，提示用户
   * - 失败时写入 error 字段，UI 显示并可重试
   */
  const loadChildren = useCallback(async (parentId: string) => {
    const raw = rawRef.current.get(parentId);
    if (!raw || raw.loading || (raw.loadedFwd && raw.loadedBwd)) return;

    syncNode(parentId, { loading: true, error: undefined });

    try {
      const { getCallees, getCallers } = await import("@/api/call-edges");
      const [callees, callers] = await Promise.all([
        getCallees(parentId).catch((e) => { console.error("getCallees error:", e); return []; }),
        getCallers(parentId).catch((e) => { console.error("getCallers error:", e); return []; }),
      ]);

      const newRaws: RawNode[] = [];
      const newEdges: Edge[] = [];
      const nowRaws = rawRef.current;
      const pendingEntry: { fwd: any[]; bwd: any[] } = { fwd: [], bwd: [] };

      const process = (items: any[], dir: "forward" | "backward") => {
        if (items.length === 0) return;

        // 全局节点数上限检查
        const remaining = MAX_TOTAL_NODES - nowRaws.size;
        if (remaining <= 0) {
          setGlobalError(`已达节点数上限（${MAX_TOTAL_NODES}），请关闭部分节点后再展开`);
          return;
        }

        // 本次允许新增的节点数（不超过单次上限，也不超过全局剩余配额）
        const allowed = Math.min(MAX_NODES_PER_EXPANSION, remaining);
        const limitedItems = items.slice(0, allowed);
        const overflow = items.slice(allowed);

        if (dir === "forward") pendingEntry.fwd = overflow;
        else pendingEntry.bwd = overflow;

        for (const item of limitedItems) {
          const calleeOrCaller = dir === "forward" ? item.callee : item.caller;
          const childId = calleeOrCaller?.id || `${parentId}-${item.call_name || "ext"}-${dir}-${Math.random().toString(36).slice(2, 8)}`;
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
              loadedFwd: isExternal,
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
            type: "chainEdge",
            data: { callType: item.call_type || "unknown" },
          });
        }
      };

      process(callees, "forward");
      process(callers, "backward");

      // 保存 pending，用于 "+N" 徽章点击时加载更多
      if (pendingEntry.fwd.length > 0 || pendingEntry.bwd.length > 0) {
        pendingRef.current.set(parentId, pendingEntry);
      } else {
        pendingRef.current.delete(parentId);
      }

      // 合并新边到 rfEdges
      if (newEdges.length > 0) {
        for (const e of newEdges) {
          rfEdges.current.set(e.id, e);
        }
      }

      // 使用 ELK 布局计算位置
      const posMap = await computeLayout();

      // 关键修复：syncNode 触发 UI 更新，包括 pendingFwd/pendingBwd
      syncNode(parentId, {
        loadedFwd: true,
        loadedBwd: true,
        loading: false,
        pendingFwd: pendingEntry.fwd.length,
        pendingBwd: pendingEntry.bwd.length,
        error: undefined,
      });

      // 批量更新 RF 节点位置
      if (isMountedRef.current) {
        setRfNodes((prev) => {
          const next = new Map(prev);
          for (const nr of newRaws) {
            next.set(nr.id, makeRfNode(nr, false, posMap.get(nr.id) || { x: 0, y: 0 }));
          }
          for (const [id, oldNode] of next) {
            const pos = posMap.get(id);
            if (pos) next.set(id, { ...oldNode, position: pos });
          }
          return next;
        });

        setRfEdgesState(new Map(rfEdges.current));

        setTimeout(() => {
          if (isMountedRef.current) {
            (rfInstance as any)?.fitView?.({ duration: 200, padding: 0.15 });
          }
        }, 150);
      }
    } catch (error) {
      console.error("loadChildren error:", error);
      syncNode(parentId, {
        loading: false,
        error: error instanceof Error ? error.message : "加载失败",
      });
    }
  }, [rfInstance, syncNode, computeLayout]);

  /**
   * 加载更多：从 pendingRef 中取出剩余项，按 LOAD_MORE_BATCH 批量追加。
   * 用于点击 "+N" 徽章时使用。
   */
  const loadMore = useCallback(async (parentId: string) => {
    const pending = pendingRef.current.get(parentId);
    if (!pending) return;
    const raw = rawRef.current.get(parentId);
    if (!raw) return;

    const nowRaws = rawRef.current;
    const remaining = MAX_TOTAL_NODES - nowRaws.size;
    if (remaining <= 0) {
      setGlobalError(`已达节点数上限（${MAX_TOTAL_NODES}）`);
      return;
    }

    const allowed = Math.min(LOAD_MORE_BATCH, remaining);
    const newRaws: RawNode[] = [];
    const newEdges: Edge[] = [];

    const consume = (queue: any[], dir: "forward" | "backward") => {
      const taken = queue.splice(0, allowed);
      for (const item of taken) {
        const calleeOrCaller = dir === "forward" ? item.callee : item.caller;
        const childId = calleeOrCaller?.id || `${parentId}-${item.call_name || "ext"}-${dir}-${Math.random().toString(36).slice(2, 8)}`;
        if (nowRaws.has(childId)) continue;

        const childDepth = dir === "forward" ? raw.depth + 1 : raw.depth - 1;
        const isExternal = !calleeOrCaller;
        const nr: RawNode = {
          id: childId,
          name: calleeOrCaller?.name || item.call_name || "(未知)",
          nodeType: calleeOrCaller?.node_type || "call",
          filePath: calleeOrCaller?.file_path,
          callName: item.call_name,
          callType: item.call_type || "unknown",
          depth: childDepth,
          parentId,
          loadedFwd: isExternal,
          loadedBwd: isExternal,
          loading: false,
        };
        newRaws.push(nr);
        nowRaws.set(childId, nr);

        newEdges.push({
          id: `${parentId}-${childId}-${dir}-${Date.now()}`,
          source: dir === "forward" ? parentId : childId,
          target: dir === "forward" ? childId : parentId,
          label: item.call_name || "",
          type: "chainEdge",
          data: { callType: item.call_type || "unknown" },
        });
      }
    };

    consume(pending.fwd, "forward");
    consume(pending.bwd, "backward");

    // 如果 pending 都消费完了，删除 entry
    if (pending.fwd.length === 0 && pending.bwd.length === 0) {
      pendingRef.current.delete(parentId);
    }

    for (const e of newEdges) {
      rfEdges.current.set(e.id, e);
    }

    const posMap = await computeLayout();

    // 更新父节点的 pending 计数
    syncNode(parentId, {
      pendingFwd: pending.fwd.length,
      pendingBwd: pending.bwd.length,
    });

    if (isMountedRef.current) {
      setRfNodes((prev) => {
        const next = new Map(prev);
        for (const nr of newRaws) {
          next.set(nr.id, makeRfNode(nr, false, posMap.get(nr.id) || { x: 0, y: 0 }));
        }
        for (const [id, oldNode] of next) {
          const pos = posMap.get(id);
          if (pos) next.set(id, { ...oldNode, position: pos });
        }
        return next;
      });
      setRfEdgesState(new Map(rfEdges.current));

      setTimeout(() => {
        if (isMountedRef.current) {
          (rfInstance as any)?.fitView?.({ duration: 200, padding: 0.15 });
        }
      }, 150);
    }
  }, [rfInstance, syncNode, computeLayout]);

  /**
   * 收起某节点的子树：移除该节点下游（forward 方向）的所有非 root 节点。
   * 用于右键菜单或"收起"按钮。
   * 支持退出动画：先标记 isExiting，动画播放完后再真正移除。
   */
  const collapseSubtree = useCallback((nodeId: string) => {
    const nowRaws = rawRef.current;
    const root = nowRaws.get(nodeId);
    if (!root) return;

    // 找出所有以 nodeId 为 ancestor 的节点（forward + backward 方向）
    const toRemove = new Set<string>();
    const queue = [nodeId];
    while (queue.length > 0) {
      const cur = queue.shift()!;
      for (const [id, r] of nowRaws) {
        if (r.parentId === cur && !toRemove.has(id)) {
          toRemove.add(id);
          queue.push(id);
        }
      }
    }

    if (toRemove.size === 0) return;

    // 先标记所有待移除节点为 isExiting，触发退出动画
    setRfNodes((prev) => {
      const next = new Map(prev);
      for (const id of toRemove) {
        const n = next.get(id);
        if (n) {
          next.set(id, {
            ...n,
            data: { ...n.data, isExiting: true },
          });
        }
      }
      return next;
    });

    // 动画结束后真正移除
    const timer = setTimeout(() => {
      // 清理 rawRef
      for (const id of toRemove) {
        nowRaws.delete(id);
        pendingRef.current.delete(id);
      }

      // 清理 edges
      const newEdgeMap = new Map<string, Edge>();
      for (const [id, e] of rfEdges.current) {
        if (!toRemove.has(e.source) && !toRemove.has(e.target)) {
          newEdgeMap.set(id, e);
        }
      }
      rfEdges.current = newEdgeMap;

      // 重置 root 的加载状态，允许重新展开
      syncNode(nodeId, {
        loadedFwd: false,
        loadedBwd: false,
        pendingFwd: 0,
        pendingBwd: 0,
      });

      if (isMountedRef.current) {
        setRfNodes((prev) => {
          const next = new Map(prev);
          for (const id of toRemove) next.delete(id);
          return next;
        });
        setRfEdgesState(new Map(newEdgeMap));

        setTimeout(() => {
          if (isMountedRef.current) {
            (rfInstance as any)?.fitView?.({ duration: 200, padding: 0.15 });
          }
        }, 50);
      }

      exitTimersRef.current.delete(nodeId);
    }, NODE_EXIT_DURATION * 1000 + 20);

    exitTimersRef.current.set(nodeId, timer);
  }, [syncNode, rfInstance]);

  /**
   * 节点点击（原路按步折叠 + 按需展开）：
   * - 有 +N 徽章（pendingFwd+pendingBwd > 0）：加载更多
   * - 有错误：重试
   * - 未加载：开始加载（首次展开）
   * - 已加载且无 pending：折叠子树（原路按步折叠，root 节点除外）
   *
   * 折叠语义：用户点击已展开的节点，移除其所有后代节点（forward+backward），
   * 并重置该节点的加载状态，允许再次点击重新展开。这就是"原路按步折叠"。
   */
  const handleNodeClick = useCallback((_event: any, node: any) => {
    const raw = rawRef.current.get(node.id);
    if (!raw) return;

    const totalPending = (raw.pendingFwd || 0) + (raw.pendingBwd || 0);
    if (totalPending > 0) {
      loadMore(node.id);
      return;
    }

    if (raw.error) {
      // 重试：重置加载状态
      syncNode(node.id, { loadedFwd: false, loadedBwd: false, error: undefined });
      setTimeout(() => loadChildren(node.id), 0);
      return;
    }

    const bothLoaded = raw.loadedFwd && raw.loadedBwd;
    if (!bothLoaded && !raw.loading) {
      // 未加载：首次展开
      loadChildren(node.id);
      return;
    }

    // 已加载且无 pending：折叠子树（root 节点除外）
    if (bothLoaded && node.id !== nodeId) {
      collapseSubtree(node.id);
    }
  }, [loadChildren, loadMore, syncNode, collapseSubtree, nodeId]);

  /**
   * 节点右键：收起子树
   */
  const handleNodeContextMenu = useCallback((event: ReactMouseEvent, node: Node) => {
    event.preventDefault();
    if (node.id === nodeId) return; // root 不允许收起
    collapseSubtree(node.id);
  }, [nodeId, collapseSubtree]);

  const nodes = useMemo(() => [...rfNodes.values()], [rfNodes]);
  const edges = useMemo(() => [...rfEdgesState.values()], [rfEdgesState]);

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

        {/* 全局错误提示 */}
        {globalError && (
          <div className="px-6 py-2 bg-amber-50 border-b border-amber-100 text-xs text-amber-700 flex items-center justify-between">
            <span>⚠ {globalError}</span>
            <button
              onClick={() => setGlobalError(null)}
              className="text-amber-500 hover:text-amber-700 ml-2"
            >✕</button>
          </div>
        )}

        {/* React Flow 画布 */}
        <div className="flex-1 overflow-hidden" style={{ position: "relative", minHeight: 0 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            onNodeClick={handleNodeClick}
            onNodeContextMenu={handleNodeContextMenu}
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
            <span>节点: {nodes.length}/{MAX_TOTAL_NODES}</span>
            <span>边: {edges.length}</span>
            <span className="text-gray-300">|</span>
            <span className="text-gray-500">点击节点展开/折叠 · +N 加载更多 · 右键收起子树</span>
          </div>
        </div>
      </div>
    </div>
  );
}
