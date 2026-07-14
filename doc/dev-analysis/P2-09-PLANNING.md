# P2-09 规划报告：调用图前端可视化

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-09 |
| 任务名称 | 调用图前端可视化（API + 渲染组件） |
| 开发日期 | 2026-07-14 |
| 开发人 | Trae AI |
| 状态 | ⬜ 规划中 |

---

## 一、现状分析

### 1.1 后端已有基础（可复用）

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| `CallEdgeModel` ORM | `codeinsight/models/call_edge.py` | ✅ 完成 | 调用边数据库模型 |
| `CallEdge` Pydantic Schema | `codeinsight/schemas/call_edge.py` | ✅ 完成 | 接口数据模型 |
| `CallEdgeDAO` | `codeinsight/repositories/call_edge.py` | ✅ 完成 | CRUD + 正向/反向查询 |
| `CallGraphBuilder` | `codeinsight/analyzers/call_graph.py` | ✅ 完成 | 调用图构建（从 call 节点 → 函数节点匹配） |
| `CallGraphQuery` | `codeinsight/analyzers/call_graph.py` | ✅ 完成 | 正向/反向/调用链查询 |

### 1.2 缺失部分

| 缺失项 | 说明 |
|--------|------|
| 🔴 **后端 API 路由** | 调用边数据未通过 FastAPI 暴露，前端无法访问 |
| 🔴 **前端 API 客户端** | 无 `getCallEdges()` 等函数 |
| 🔴 **调用图渲染组件** | 无可视化组件 |
| 🔴 **图表库依赖** | 前端无 graph 可视化库（需引入 `reactflow`） |

### 1.3 当前文件页面布局

```
┌────────────────────┬─────────────────────────────────┐
│  文件树（FileTree） │  代码结构（StructureList）      │
│                    │  • 按 depth 缩进列表            │
│  左侧 ~50%        │  • NodeBadge 类型标签            │
│                    │  • 行号范围 L1-L10              │
└────────────────────┴─────────────────────────────────┘
```

点击文件后右侧仅展示 **结构概览**（函数/类/方法列表），没有调用关系可视化。

---

## 二、目标与范围

### 2.1 核心目标

在选择文件后，新增"**调用图**"标签页/面板，可视化展示该文件中函数之间的调用关系。

### 2.2 交付范围

| 模块 | 交付物 | 说明 |
|------|--------|------|
| 后端 API | `GET /api/v1/call-edges` | 按 file_id 或 node_id 查询调用边 |
| 后端 API | `GET /api/v1/call-edges/{node_id}/callers` | 查询调用某节点的所有调用者（反向） |
| 后端 API | `GET /api/v1/call-edges/{node_id}/callees` | 查询该节点调用的所有目标（正向） |
| 前端 API | `getCallEdges()` | API 客户端函数 |
| 前端组件 | `CallGraph` | React Flow 可视化组件 |
| 前端集成 | 文件页面新增"调用图"标签页 | 与结构概览并列展示 |

### 2.3 不在本阶段范围

| 排除项 | 原因 |
|--------|------|
| 跨文件调用图（全仓库级别） | 首阶段仅展示当前文件内部调用；全仓库在 P3 实现 |
| 交互式拖拽/缩放 | `reactflow` 内置支持，首阶段直接使用 |
| 调用链高亮路径 | P3 阶段增强 |

---

## 三、后端设计

### 3.1 API 路由设计

新增文件：`codeinsight/api/call_edges.py`

| 方法 | 路径 | 参数 | 返回 | 说明 |
|------|------|------|------|------|
| `GET` | `/api/v1/call-edges` | `file_id?`, `repository_id?`, `node_type?` | `list[CallEdgeResponse]` | 按文件/仓库/节点类型过滤 |
| `GET` | `/api/v1/call-edges/{node_id}/callees` | `node_id` (UUID) | `list[CallEdgeWithNode]` | 该节点调用的所有目标（含 callee 节点详情） |
| `GET` | `/api/v1/call-edges/{node_id}/callers` | `node_id` (UUID) | `list[CallEdgeWithNode]` | 调用该节点的所有调用者（含 caller 节点详情） |

### 3.2 响应 Schema

```python
class CallEdgeResponse(BaseModel):
    """调用边响应"""
    id: UUID
    repository_id: UUID
    caller_node_id: UUID
    callee_node_id: UUID | None = None
    call_name: str
    call_type: str          # "static" | "dynamic" | "unknown"
    start_line: int
    start_column: int

class CallEdgeWithNode(CallEdgeResponse):
    """含节点详情的调用边（用于正向/反向查询）"""
    caller: AstNode | None = None   # 调用者节点信息
    callee: AstNode | None = None   # 被调用者节点信息（可为 None）
```

### 3.3 关键实现逻辑

```python
@router.get("/call-edges/{node_id}/callees")
async def get_callees(node_id: UUID, db: DbSession):
    """获取该节点调用的所有目标"""
    query = CallGraphQuery()
    callees = await query.get_callees(node_id, db=db)
    return callees
```

**数据来源**：直接从 `CallGraphQuery.get_callees()` 返回的字典列表序列化为响应。

---

## 四、前端设计

### 4.1 新增依赖

```bash
npm install @xyflow/react   # React Flow (官方 12.x 包名)
```

### 4.2 前端 API 客户端

新增文件：`codeinsight-frontend/src/api/call-edges.ts`

```typescript
import { apiFetch } from "./base";

export async function getCallEdges(params: {
  file_id?: string;
  repository_id?: string;
}): Promise<CallEdge[]> {
  // GET /api/v1/call-edges?file_id=...
}

export async function getCallers(nodeId: string): Promise<CallEdgeWithNode[]> {
  // GET /api/v1/call-edges/{node_id}/callers
}

export async function getCallees(nodeId: string): Promise<CallEdgeWithNode[]> {
  // GET /api/v1/call-edges/{node_id}/callees
}
```

### 4.3 数据钩子

在 `use-files.ts` 中新增：

```typescript
export function useCallEdges(params: { file_id?: string; repository_id?: string }) {
  return useQuery({
    queryKey: ["call-edges", params],
    queryFn: () => getCallEdges(params),
    enabled: !!params.file_id || !!params.repository_id,
    staleTime: 2 * 60 * 1000,
  });
}

export function useCallees(nodeId: string | null) {
  return useQuery({
    queryKey: ["callers", nodeId],
    queryFn: () => getCallees(nodeId!),
    enabled: !!nodeId,
    staleTime: 1 * 60 * 1000,
  });
}
```

### 4.4 调用图组件设计

新增文件：`codeinsight-frontend/src/components/call-graph/`

```
src/components/call-graph/
├── CallGraph.tsx          ← 主组件（React Flow 容器）
├── CallNode.tsx           ← 自定义节点（不同 node_type 颜色/图标）
├── CallEdge.tsx           ← 自定义边（箭头样式，call_type 虚线区分）
└── index.ts               ← 入口导出
```

### 4.5 组件接口

```typescript
interface CallGraphProps {
  fileId: string;
  /** 高亮的节点 ID（选中该节点的调用关系） */
  selectedNodeId?: string;
}
```

### 4.6 渲染逻辑

1. 通过 `useCallEdges({ file_id })` 获取该文件的所有调用边
2. 通过 `useAstNodes({ file_id })` 获取该文件的所有 AST 节点（用于节点位置）
3. 构建 React Flow 数据：
   - **Nodes**：该文件中的所有函数/方法/构造器节点（`node_type ∈ {function, method, constructor}`）
   - **Edges**：调用边（从 `caller_node_id` → `callee_node_id`）
4. 使用 `useNodesState` / `useEdgesState` 管理交互状态

### 4.7 节点分类与样式

| node_type | 颜色 | 形状 | 图标 |
|-----------|------|------|------|
| `function` | 蓝色 `#3b82f6` | 圆角矩形 | 🔧 |
| `method` | 紫色 `#8b5cf6` | 圆角矩形 | ⚙️ |
| `constructor` | 橙色 `#f59e0b` | 菱形 | 🏗️ |

### 4.8 边样式

| call_type | 样式 | 说明 |
|-----------|------|------|
| `static` | 实线箭头 | 精确匹配的调用 |
| `dynamic` | 虚线箭头 | 动态调用（getattr 等） |
| `unknown` | 点线箭头 + 半透明 | 未知调用 |

### 4.9 页面集成

修改 `src/app/repositories/[repo_id]/files/page.tsx`，右侧面板改为**标签页切换**：

```
┌────────────────────┬─────────────────────────────────┐
│  文件树（FileTree） │  🏷️ 代码结构  |  📊 调用图    │
│                    │  ─────────────────────────────  │
│                    │  [标签内容区域]                 │
│                    │                                 │
└────────────────────┴─────────────────────────────────┘
```

---

## 五、数据流

```
用户点击文件 → 选中 fileId
    │
    ▼
┌─────────────────────────────────────┐
│ useCallEdges({ file_id })           │
│   GET /api/v1/call-edges?file_id=   │
│   2 分钟缓存                         │
└─────────────────────────────────────┘
    │
    ▼  解析 edges_data
    │  • nodes: 所有 function/method/constructor
    │  • edges: caller_node_id → callee_node_id
    ▼
┌─────────────────────────────────────┐
│ CallGraph 组件 (React Flow)         │
│                                     │
│  Nodes:  文件中的函数/方法/构造器    │
│  Edges:  调用边（实线/虚线/点线）    │
│                                     │
│  交互:                               │
│  • 拖拽节点                         │
│  • 缩放/平移                        │
│  • 点击节点 → 高亮相关调用链        │
│  • 点击边 → 显示调用详情            │
└─────────────────────────────────────┘
    │
    ▼  点击节点时触发
┌─────────────────────────────────────┐
│ useCallees(nodeId)                  │
│   GET /api/v1/call-edges/{id}/callees│
│   1 分钟缓存                         │
└─────────────────────────────────────┘
    │
    ▼  高亮显示相关边
```

---

## 六、目录结构（最终）

```
codeinsight-backend/
└── codeinsight/
    └── api/
        ├── call_edges.py       ← 新增：调用边 API 路由（3 个端点）
        └── ...

codeinsight-frontend/
├── src/
│   ├── api/
│   │   └── call-edges.ts       ← 新增：调用边 API 客户端
│   ├── hooks/
│   │   └── use-files.ts        ← 修改：新增 useCallEdges/useCallees
│   ├── components/
│   │   └── call-graph/
│   │       ├── CallGraph.tsx   ← 新增：React Flow 容器
│   │       ├── CallNode.tsx    ← 新增：自定义节点
│   │       ├── CallEdge.tsx    ← 新增：自定义边
│   │       └── index.ts        ← 新增：入口导出
│   └── app/
│       └── repositories/
│           └── [repo_id]/
│               └── files/
│                   └── page.tsx ← 修改：新增调用图标签页
```

---

## 七、设计决策记录

| # | 决策 | 方案 | 理由 |
|---|------|------|------|
| 1 | 图表库选择 | `@xyflow/react`（React Flow 12.x） | React 原生，内置拖拽/缩放/碰撞检测；比 D3 更简单，比 Cytoscape 更轻量 |
| 2 | 节点布局算法 | React Flow 内置自动布局 + 手动拖拽 | 首阶段不实现自动布局算法，使用默认力导向布局 |
| 3 | 跨文件调用 | 首阶段不展示 | 全仓库调用图节点数爆炸，P3 阶段再做增量实现 |
| 4 | 调用链高亮 | 点击节点后查询 callees 并高亮相关边 | 保持交互简单，逐步深入 |
| 5 | 边方向 | caller → callee（从左到右） | 符合代码阅读习惯 |
| 6 | call_type 视觉区分 | 实线/虚线/点线三种样式 | 直观区分静态、动态、未知调用 |

---

## 八、技术选型对比

| 库 | 优势 | 劣势 | 结论 |
|----|------|------|------|
| `@xyflow/react` | React 原生，文档完善，社区活跃 | 需 npm 安装（~300KB） | ✅ 推荐 |
| `react-cytoscapejs` | 强大的布局算法 | React 封装较厚，API 复杂 | ❌ 过度设计 |
| `react-d3-graph` | 无需额外安装 | 自定义能力弱，维护不活跃 | ❌ 不合适 |
| `mermaid.js` | 零配置 | 非交互，无法拖拽/缩放 | ❌ 不满足需求 |

---

## 九、验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| 1 | 选择文件后，调用图标签页正常显示 | 手动测试 |
| 2 | 函数节点按 type 显示不同颜色 | 视觉验证 |
| 3 | 调用边按 call_type 显示不同样式 | 视觉验证 |
| 4 | 支持拖拽节点、缩放/平移 | 手动测试 |
| 5 | 点击节点高亮相关调用边 | 手动测试 |
| 6 | 空文件（无调用）显示友好提示 | 手动测试 |
| 7 | 后端 API 返回正确数据 | pytest 测试 |
| 8 | 通过 ruff + mypy 检查 | CI |
| 9 | 通过 ESLint + tsc 检查 | CI |

---

## 十、与规划对比（预估）

| 规划项 | 预估 |
|--------|------|
| 后端 API 路由（1 文件） | ~100 行 |
| 前端 API 客户端（1 文件） | ~30 行 |
| 调用图组件（4 文件） | ~200 行 |
| 页面集成修改（1 文件） | ~50 行修改 |
| 新增测试（后端） | ~20 个用例 |
| 新增依赖（1 个） | `@xyflow/react` |
| **合计** | **~5 个新增文件，3 个修改文件** |

---

**编制日期**: 2026-07-14  
**编制人**: Trae AI  
**任务编号**: P2-09  
**状态**: ⬜ 规划中
