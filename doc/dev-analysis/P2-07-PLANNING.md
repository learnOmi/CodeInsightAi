# P2-07: 解析结果前端预览 — 文件树 + 结构概览

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-07 |
| 任务名称 | 解析结果前端预览：文件树 + 结构概览 |
| 所属阶段 | Phase 2（第 4-6 周） |
| 优先级 | P1 |
| 预估工时 | 10h |
| 交付物 | 文件树组件 + 代码结构面板 + AST 节点 API |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P2-01 GitScanner | ✅ | 文件列表数据源（`/api/files` API 已就绪） |
| P2-02 Tree-sitter 解析层 | ✅ | 5 种语言解析器已实现，AST 数据已入库 |
| P2-04 结构分析引擎 | ✅ | 调用图 + 模块依赖图已构建 |
| P2-05 结构数据入库管道 | ✅ | AST 节点、调用边、模块依赖已持久化 |
| P1-07 DAO 层 | ✅ | `AstNodeDAO` 提供节点查询 |
| P1-08 Celery 异步任务 | ✅ | 分析进度追踪已就绪 |
| 前端骨架 | ✅ | Next.js 15 + Tailwind + Zustand 已搭建 |

### 任务背景

当前前端仅有仓库列表（`/repositories`）和空白的知识库/搜索页面。P2-07 是**前端第一个核心功能**，需要实现：

1. **文件树** — 以树形结构展示代码仓库的文件目录，支持折叠/展开
2. **代码结构概览** — 选中文件后，显示该文件的 AST 结构（函数、类、方法等）
3. **分析状态展示** — 显示当前分析任务的状态（进行中/已完成/失败）和进度

这是连接后端分析结果与前端用户界面的**第一个关键桥梁**，为后续 P4（知识卡片、代码链路查看器）奠定组件和数据流基础。

---

## 二、整体架构位置

P2-07 是前端展示层的**第一个数据密集型页面**，与后端 API 的对接关系如下：

```
┌────────────────────────────────────────────────────────────────────┐
│  前端展示层 (Next.js 15 + App Router)                               │
│                                                                     │
│  /repositories/{repo_id}/files  ←── P2-07 新页面                   │
│  ├── [左侧面板] 文件树组件 (FileTree)                               │
│  │   API: GET /api/files?repository_id={id}                        │
│  │   └── 递归构建树形结构（基于 file.path 的目录层级）              │
│  │                                                                     │
│  ├── [右侧面板] 结构概览组件 (StructureOverview)                    │
│  │   API: GET /api/ast-nodes?file_id={id}                        │
│  │   └── 以树形/列表展示该文件的函数、类、方法                      │
│  │                                                                     │
│  └── [顶部栏] 分析状态 (AnalysisStatusBadge)                        │
│      API: GET /api/repositories/{id} / GET /api/analysis/versions/{id}│
│      └── 显示当前分析状态 + 进度条                                   │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  后端 API 层 (FastAPI)                                              │
│  ├── GET  /api/files?repository_id={id}&page={n}&page_size={n}     │
│  │   已就绪：返回分页文件列表（含 path, absolute_path, language）  │
│  │                                                                     │
│  ├── GET  /api/ast-nodes?file_id={id}  ←── 需要新增               │
│  │   返回该文件的 AST 节点列表（含 node_type, name, line 范围）    │
│  │                                                                     │
│  └── GET  /api/repositories/{id}                                    │
│      已就绪：返回仓库状态（status, current_version, file_count）   │
└────────────────────────────────────────────────────────────────────┘
```

### 2.1 页面路由结构

```
/app/
├── repositories/
│   ├── page.tsx                    ← 仓库列表（已实现）
│   └── [repo_id]/                  ← P2-07 新增
│       ├── layout.tsx              ← 仓库详情页布局（左右分栏）
│       ├── files/
│       │   └── page.tsx            ← 文件树 + 结构概览
│       ├── structures/
│       │   └── page.tsx            ← P4 预留给代码链路查看器
│       └── knowledge/
│           └── page.tsx            ← P4 预留给知识卡片
```

---

## 三、新增模块结构

```
codeinsight-frontend/
├── src/
│   ├── app/
│   │   ├── repositories/
│   │   │   └── [repo_id]/
│   │   │       ├── layout.tsx              ← 新增：仓库详情布局
│   │   │       └── files/
│   │   │           └── page.tsx            ← 新增：文件树 + 结构概览页面
│   │   │
│   │   ├── api/
│   │   │   ├── files.ts                    ← 新增：文件列表 API 客户端
│   │   │   ├── ast-nodes.ts                ← 新增：AST 节点 API 客户端
│   │   │   └── analysis.ts                 ← 新增：分析状态 API 客户端
│   │   │
│   │   ├── components/
│   │   │   ├── file-tree/                  ← 新增：文件树组件组
│   │   │   │   ├── index.tsx
│   │   │   │   ├── TreeNode.tsx            ← 可折叠文件节点
│   │   │   │   └── TreeView.tsx            ← 完整文件树视图
│   │   │   ├── structure/                  ← 新增：结构概览组件组
│   │   │   │   ├── index.tsx
│   │   │   │   ├── StructureList.tsx       ← 节点列表展示
│   │   │   │   └── NodeBadge.tsx           ← 节点类型标签（function/class/method）
│   │   │   └── analysis-status/            ← 新增：分析状态组件
│   │   │       ├── index.tsx
│   │   │       ├── StatusBadge.tsx         ← 状态徽标（待分析/分析中/已完成/失败）
│   │   │       └── ProgressRing.tsx        ← 进度环形指示器
│   │   │
│   │   ├── hooks/
│   │   │   ├── use-files.ts                ← 新增：文件列表数据钩子
│   │   │   ├── use-ast-nodes.ts            ← 新增：AST 节点数据钩子
│   │   │   └── use-analysis-status.ts      ← 新增：分析状态数据钩子
│   │   │
│   │   └── lib/
│   │       ├── tree-utils.ts               ← 新增：文件树构建工具函数
│   │       └── structure-utils.ts          ← 新增：结构概览工具函数
│   │
│   └── styles/
│       └── globals.css                     ← 可能增加树形结构相关样式

codeinsight-backend/
├── codeinsight/
│   ├── api/
│   │   └── ast_nodes.py                    ← 新增：AST 节点 API 路由
│   │
│   └── repositories/
│       └── ast_node.py                     ← 修改：新增按 file_id 查询方法

packages/shared/
├── src/
│   ├── constants.ts                        ← 新增：前端常量（节点类型映射、分析状态）
│   └── types.ts                            ← 可能新增：共享类型
│
└── test/
    ├── __tests__/
    │   ├── file-tree.test.tsx              ← 新增：文件树组件测试
    │   ├── structure-list.test.tsx         ← 新增：结构概览组件测试
    │   ├── status-badge.test.tsx           ← 新增：状态徽标测试
    │   └── tree-utils.test.ts              ← 新增：树构建工具测试
```

---

## 四、后端 API 变更

### 4.1 新增：AST 节点 API 路由

```python
"""
AST 节点路由

提供 AST 节点的查询接口，供前端结构概览使用。
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.db.session import get_db_session
from codeinsight.repositories.ast_node import AstNodeDAO
from codeinsight.schemas.ast_node import AstNode

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)

def get_ast_node_dao() -> AstNodeDAO:
    return AstNodeDAO()

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AstNodeDaoDep = Annotated[AstNodeDAO, Depends(get_ast_node_dao)]


@router.get("")
async def list_ast_nodes(
    file_id: Annotated[UUID | None, Query(description="文件 ID（可选，查询指定文件的节点）")] = None,
    repository_id: Annotated[UUID | None, Query(description="仓库 ID（可选）")] = None,
    node_type: Annotated[str | None, Query(description="节点类型过滤")] = None,
    db: DbSession = None,
    dao: AstNodeDaoDep = None,
):
    """
    获取 AST 节点列表

    支持按文件、仓库、节点类型过滤。
    若不提供 file_id 和 repository_id，返回空列表。
    """
    if file_id:
        nodes = await dao.get_by_file_id(db, file_id)
    elif repository_id:
        nodes = await dao.get_by_repository(db, repository_id)
    else:
        return []

    if node_type:
        nodes = [n for n in nodes if n.node_type == node_type]

    return [AstNode.model_validate(n) for n in nodes]


@router.get("/{node_id}", response_model=AstNode)
async def get_ast_node(
    node_id: UUID,
    db: DbSession,
    dao: AstNodeDaoDep,
):
    """获取单个 AST 节点详情"""
    node = await dao.get_by_id(db, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"AST node {node_id} not found")
    return node
```

### 4.2 修改：AstNodeDAO 新增按 file_id 查询

```python
# 在 existing AstNodeDAO 中新增：

async def get_by_file_id(
    self, db: AsyncSession, file_id: UUID
) -> list[AstNodeModel]:
    """
    获取指定文件的所有 AST 节点

    Args:
        db: 数据库 session
        file_id: 文件 ID

    Returns:
        该文件的 AST 节点列表（按 start_line 排序）
    """
    result = await db.execute(
        select(AstNodeModel)
        .where(AstNodeModel.file_id == file_id)
        .order_by(AstNodeModel.start_line)
    )
    return list(result.scalars().all())
```

---

## 五、前端组件设计

### 5.1 文件树组件 (`FileTree`)

```tsx
// components/file-tree/TreeView.tsx

type FileTreeProps = {
  repositoryId: string;
  onSelectFile: (fileId: string, filePath: string) => void;
  selectedFileId?: string;
};

export function TreeView({ repositoryId, onSelectFile, selectedFileId }: FileTreeProps) {
  // 1. 获取文件列表
  const { data: files, isLoading, error } = useFiles(repositoryId);

  // 2. 将扁平文件列表转换为树结构
  const tree = useMemo(() => buildFileTree(files ?? []), [files]);

  // 3. 渲染树
  return (
    <div className="file-tree">
      {isLoading ? (
        <Skeleton count={5} />
      ) : error ? (
        <ErrorAlert message="加载文件列表失败" />
      ) : (
        <div className="space-y-1">
          {tree.map((node) => (
            <TreeNode
              key={node.id ?? node.path}
              node={node}
              onSelect={onSelectFile}
              selectedId={selectedFileId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

**树节点渲染规则：**

| 节点类型 | 图标 | 行为 |
|----------|------|------|
| 目录 (path 以 `/` 结尾) | 📁/📂 | 可折叠/展开 |
| 文件 (有文件扩展名) | 📄/📝 | 可点击选中，显示右侧结构概览 |
| 二进制/非源码文件 | 🔒 | 不可点击，灰色显示 |

**文件类型图标映射：**

```ts
const FILE_ICONS: Record<string, string> = {
  ".py": "🐍",
  ".js": "⚡",
  ".ts": "📘",
  ".tsx": "⚛️",
  ".java": "☕",
  ".go": "🔵",
  ".rs": "🦀",
  ".cpp": "🔶",
  ".h": "🔷",
  ".css": "🎨",
  ".json": "📋",
  ".md": "📝",
  default: "📄",
};
```

### 5.2 结构概览组件 (`StructureOverview`)

```tsx
// components/structure/StructureList.tsx

type StructureListProps = {
  fileId: string;
  fileName: string;
};

export function StructureList({ fileId, fileName }: StructureListProps) {
  const { data: nodes, isLoading } = useAstNodes({ file_id: fileId });

  // 按缩进层级分组（parent_node_id 表示父子关系）
  const grouped = useMemo(() => groupByParent(nodes ?? []), [nodes]);

  return (
    <div className="structure-list">
      <h3 className="text-lg font-semibold mb-3">{fileName}</h3>
      {isLoading ? (
        <Skeleton count={8} />
      ) : nodes.length === 0 ? (
        <div className="text-muted text-sm">该文件暂无解析结果</div>
      ) : (
        <ul className="space-y-1">
          {grouped.map((node) => (
            <li key={node.id} style={{ paddingLeft: node.depth * 16 }}>
              <NodeBadge type={node.node_type}>
                {node.name}
              </NodeBadge>
              <span className="text-xs text-muted">
                :{node.start_line}-{node.end_line}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

### 5.3 分析状态组件 (`AnalysisStatusBadge`)

```tsx
// components/analysis-status/StatusBadge.tsx

const STATUS_CONFIG = {
  pending:     { icon: "⏳", label: "待分析",   color: "bg-gray-100 text-gray-600" },
  analyzing:   { icon: "🔄", label: "分析中",   color: "bg-blue-100 text-blue-600", animate: true },
  scanning:    { icon: "🔍", label: "扫描中",   color: "bg-blue-100 text-blue-600", animate: true },
  parsing:     { icon: "🧩", label: "解析中",   color: "bg-blue-100 text-blue-600", animate: true },
  completed:   { icon: "✅", label: "已完成",   color: "bg-green-100 text-green-600" },
  failed:      { icon: "❌", label: "失败",     color: "bg-red-100 text-red-600" },
  cancelled:   { icon: "⏹️", label: "已取消",   color: "bg-gray-100 text-gray-500" },
};

export function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;

  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${config.color}`}>
      {config.icon}
      {config.label}
    </span>
  );
}
```

### 5.4 页面布局 (`[repo_id]/layout.tsx`)

```tsx
// app/repositories/[repo_id]/layout.tsx

export default function RepoDetailLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ repo_id: string }>;
}) {
  const { repo_id } = React.use(params);

  return (
    <main className="min-h-screen bg-gray-50">
      {/* 顶部导航栏 */}
      <header className="sticky top-0 z-10 border-b bg-white">
        <div className="mx-auto max-w-7xl px-4 py-3">
          <nav className="flex items-center gap-4">
            <Link href="/repositories" className="text-muted hover:text-foreground">
              ← 仓库列表
            </Link>
            <div className="h-6 w-px bg-gray-200" />
            <RepoName repoId={repo_id} />
            <div className="ml-auto">
              <AnalysisStatusBadge repoId={repo_id} />
            </div>
          </nav>
        </div>
      </header>

      {/* 主体内容 */}
      <div className="mx-auto max-w-7xl px-4 py-6">
        {children}
      </div>
    </main>
  );
}
```

---

## 六、数据流设计

### 6.1 文件树数据流

```
用户访问 /repositories/{repo_id}/files
    │
    ▼
getRepo(repo_id)  ── GET /api/repositories/{id} ──→ { name, path, status, ... }
    │
    ▼
getFiles(repo_id, page=1, page_size=100)  ── GET /api/files?repository_id={id} ──→ [ File[] ]
    │
    ▼
buildFileTree(files)  ←── 客户端工具函数
    │
    ├── 按 path 目录层级拆分
    ├── 同名目录合并为可折叠节点
    ├── 排序：目录优先，文件其次，按字母排序
    │
    ▼
TreeView 渲染树形结构
    │
    ├── 用户点击文件
    │   ▼
    ├── getFile(file_id)  ── GET /api/files/{file_id} ──→ File
    │   │
    │   ▼
    ├── getAstNodes(file_id)  ── GET /api/ast-nodes?file_id={file_id} ──→ [ AstNode[] ]
    │   │
    │   ▼
    └── StructureList 渲染结构概览
```

### 6.2 buildFileTree 算法

```ts
// lib/tree-utils.ts

interface TreeNode {
  id?: string;
  path: string;
  name: string;
  children: TreeNode[];
  isDirectory: boolean;
  isSelected?: boolean;
}

export function buildFileTree(files: File[]): TreeNode[] {
  const root: TreeNode = { path: "", name: "", children: [], isDirectory: true };

  for (const file of files) {
    // 按路径层级拆分
    const parts = file.path.split("/").filter(Boolean);
    let current = root;

    for (const part of parts.slice(0, -1)) {
      // 查找或创建目录节点
      let child = current.children.find((c) => c.name === part && c.isDirectory);
      if (!child) {
        child = { path: `${current.path}/${part}`, name: part, children: [], isDirectory: true };
        current.children.push(child);
      }
      current = child;
    }

    // 添加文件节点
    const fileName = parts[parts.length - 1] ?? file.path;
    current.children.push({
      id: file.id,
      path: file.path,
      name: fileName,
      children: [],
      isDirectory: false,
    });
  }

  // 排序：目录优先，文件其次
  return sortChildren(root.children);
}

function sortChildren(children: TreeNode[]): TreeNode[] {
  return children.sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}
```

---

## 七、前端常量定义

### 7.1 节点类型配置

```ts
// packages/shared/src/constants.ts

export const NODE_TYPE_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  function:  { icon: "⚙️", color: "bg-blue-100 text-blue-700", label: "函数" },
  method:    { icon: "⚙️", color: "bg-blue-100 text-blue-700", label: "方法" },
  class:     { icon: "🏗️", color: "bg-purple-100 text-purple-700", label: "类" },
  interface: { icon: "📐", color: "bg-cyan-100 text-cyan-700", label: "接口" },
  module:    { icon: "📦", color: "bg-orange-100 text-orange-700", label: "模块" },
  variable:  { icon: "📌", color: "bg-gray-100 text-gray-700", label: "变量" },
  import:    { icon: "🔗", color: "bg-green-100 text-green-700", label: "导入" },
  default:   { icon: "📄", color: "bg-gray-100 text-gray-600", label: "节点" },
};

export const ANALYSIS_STATUS_CONFIG = {
  pending:     { icon: "⏳", label: "待分析",   color: "bg-gray-100 text-gray-600" },
  analyzing:   { icon: "🔄", label: "分析中",   color: "bg-blue-100 text-blue-600", animate: true },
  scanning:    { icon: "🔍", label: "扫描中",   color: "bg-blue-100 text-blue-600", animate: true },
  parsing:     { icon: "🧩", label: "解析中",   color: "bg-blue-100 text-blue-600", animate: true },
  completed:   { icon: "✅", label: "已完成",   color: "bg-green-100 text-green-600" },
  failed:      { icon: "❌", label: "失败",     color: "bg-red-100 text-red-600" },
  cancelled:   { icon: "⏹️", label: "已取消",   color: "bg-gray-100 text-gray-500" },
};
```

---

## 八、API 数据流 (TanStack Query)

### 8.1 useFiles Hook

```ts
// hooks/use-files.ts

import { useQuery } from "@tanstack/react-query";
import { getFiles } from "@/app/api/files";

export function useFiles(repoId: string, page: number = 1, pageSize: number = 100) {
  return useQuery({
    queryKey: ["files", repoId, page, pageSize],
    queryFn: () => getFiles(repoId, page, pageSize),
    staleTime: 5 * 60 * 1000, // 5 分钟缓存
  });
}
```

### 8.2 useAstNodes Hook

```ts
// hooks/use-ast-nodes.ts

import { useQuery } from "@tanstack/react-query";
import { getAstNodes } from "@/app/api/ast-nodes";

interface GetAstNodesParams {
  file_id?: string;
  repository_id?: string;
}

export function useAstNodes(params: GetAstNodesParams) {
  return useQuery({
    queryKey: ["ast-nodes", params],
    queryFn: () => getAstNodes(params),
    enabled: !!params.file_id, // 只在有 file_id 时查询
    staleTime: 2 * 60 * 1000, // 2 分钟缓存
  });
}
```

### 8.3 useAnalysisStatus Hook

```ts
// hooks/use-analysis-status.ts

import { useQuery } from "@tanstack/react-query";
import { getRepository } from "@/app/api/repositories";

export function useAnalysisStatus(repoId: string) {
  return useQuery({
    queryKey: ["repo-status", repoId],
    queryFn: () => getRepository(repoId),
    staleTime: 30 * 1000, // 30 秒轮询
    refetchInterval: (data) => {
      // 分析中时每 10 秒轮询，否则停止轮询
      return data?.status === "analyzing" ? 10_000 : undefined;
    },
  });
}
```

---

## 九、测试覆盖

### 9.1 后端测试

| 测试 | 覆盖内容 |
|------|---------|
| `test_ast_node_api_list_by_file` | 按 file_id 查询 AST 节点列表 |
| `test_ast_node_api_list_by_repository` | 按 repository_id 查询 |
| `test_ast_node_api_get_by_id` | 获取单个节点 |
| `test_ast_node_api_get_not_found` | 节点不存在返回 404 |
| `test_ast_node_dao_get_by_file_id` | DAO 层按 file_id 查询正确性 |
| `test_ast_node_dao_ordering` | 节点按 start_line 排序 |

### 9.2 前端测试

| 测试 | 覆盖内容 |
|------|---------|
| `test_build_file_tree_flat` | 平铺文件列表正确构建树 |
| `test_build_file_tree_nested` | 嵌套目录正确构建 |
| `test_build_file_tree_empty` | 空文件列表返回空树 |
| `test_build_file_tree_sorting` | 目录优先、字母排序 |
| `test_file_tree_component_render` | FileTree 组件正常渲染 |
| `test_file_tree_component_select` | 点击文件触发 onSelect 回调 |
| `test_structure_list_render` | StructureList 渲染节点列表 |
| `test_structure_list_empty` | 空节点列表显示提示信息 |
| `test_structure_list_grouping` | 按 parent_node_id 正确分组 |
| `test_status_badge_all_statuses` | 7 种状态徽标正确显示 |
| `test_use_files_hook` | useFiles hook 数据获取 |
| `test_use_ast_nodes_hook` | useAstNodes hook 条件查询 |
| `test_use_analysis_status_hook` | useAnalysisStatus hook 轮询 |

---

## 十、设计决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **文件树构建位置** | 前端客户端构建（`buildFileTree`） | 后端 API 返回扁平列表，前端灵活调整层级显示；避免后端维护树形序列化逻辑 |
| **AST 节点分组** | 前端按 `parent_node_id` 分组 | 后端仅做查询，前端根据用户需要决定展示粒度 |
| **文件列表分页** | 后端分页（page/page_size），前端一次性加载第 1 页 | 树形结构需要完整文件列表，100 条/页满足绝大多数仓库 |
| **树形组件折叠** | 本地状态管理（React useState） | 折叠状态不持久化，页面刷新重置；避免服务端存储状态 |
| **节点类型图标** | 前端常量映射（`NODE_TYPE_CONFIG`） | 不同语言可能有相同 node_type，图标按通用类型映射即可 |
| **分析状态轮询** | TanStack Query `refetchInterval` | 分析中时自动轮询，完成后停止，避免浪费资源 |
| **API Key 认证** | 复用现有 `get_api_key_dependency` | 所有 API 端点统一认证，无需额外逻辑 |
| **错误处理** | API 层统一返回 Pydantic ValidationError / HTTPException | 前端通过 TanStack Query 的 `error` 状态捕获并展示 |

---

## 十一、与 Phase 2 其他任务的关系

| 任务 | 状态 | 与 P2-07 的关系 |
|------|------|----------------|
| P2-01 GitScanner | ✅ | P2-07 使用文件列表 API 数据源 |
| P2-02 Tree-sitter 解析 | ✅ | P2-07 展示解析结果 |
| P2-04 结构分析引擎 | ✅ | P2-07 可展示调用图（Phase 4 扩展） |
| P2-05 结构数据入库 | ✅ | P2-07 数据来自已入库的 AST 节点 |
| P2-06 增量扫描 | ✅ | P2-07 文件树支持展示增量分析后的最新文件 |
| P4-01 知识卡片 | ⬜ | P2-07 为知识卡片提供文件上下文 |
| P4-03 代码链路查看器 | ⬜ | P2-07 结构概览是代码链路的基础组件 |

---

## 十二、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 搜索文件 | P4-04 | 在文件树中搜索特定文件 |
| 调用图可视化 | P4-08 | 在结构概览中展示文件的调用关系 |
| 文件内容预览 | P4-03 | 点击文件节点后展示文件源码 |
| 文件树拖拽重排 | P5 | 支持手动调整文件顺序 |
| 大仓库虚拟滚动 | P5-01 | 文件树超过 1000 节点时使用虚拟列表 |

---

## 十三、文件变更明细

### 新增文件

| 文件 | 说明 | 预估行数 |
|------|------|---------|
| `codeinsight-frontend/src/app/api/files.ts` | 文件 API 客户端 | ~30 |
| `codeinsight-frontend/src/app/api/ast-nodes.ts` | AST 节点 API 客户端 | ~30 |
| `codeinsight-frontend/src/app/api/analysis.ts` | 分析状态 API 客户端 | ~20 |
| `codeinsight-frontend/src/app/repositories/[repo_id]/layout.tsx` | 仓库详情布局 | ~40 |
| `codeinsight-frontend/src/app/repositories/[repo_id]/files/page.tsx` | 文件树 + 结构概览页面 | ~80 |
| `codeinsight-frontend/src/app/components/file-tree/index.tsx` | 文件树入口 | ~10 |
| `codeinsight-frontend/src/app/components/file-tree/TreeNode.tsx` | 树节点组件 | ~100 |
| `codeinsight-frontend/src/app/components/file-tree/TreeView.tsx` | 文件树视图 | ~60 |
| `codeinsight-frontend/src/app/components/structure/index.tsx` | 结构概览入口 | ~10 |
| `codeinsight-frontend/src/app/components/structure/StructureList.tsx` | 节点列表组件 | ~80 |
| `codeinsight-frontend/src/app/components/structure/NodeBadge.tsx` | 节点类型标签 | ~40 |
| `codeinsight-frontend/src/app/components/analysis-status/index.tsx` | 状态组件入口 | ~10 |
| `codeinsight-frontend/src/app/components/analysis-status/StatusBadge.tsx` | 状态徽标 | ~40 |
| `codeinsight-frontend/src/app/hooks/use-files.ts` | 文件列表 hook | ~15 |
| `codeinsight-frontend/src/app/hooks/use-ast-nodes.ts` | AST 节点 hook | ~20 |
| `codeinsight-frontend/src/app/hooks/use-analysis-status.ts` | 分析状态 hook | ~25 |
| `codeinsight-frontend/src/app/lib/tree-utils.ts` | 文件树构建工具 | ~60 |
| `codeinsight-frontend/src/app/lib/structure-utils.ts` | 结构概览工具 | ~30 |
| `packages/shared/src/constants.ts` | 前端常量 | ~40 |
| `codeinsight-backend/codeinsight/api/ast_nodes.py` | AST 节点 API 路由 | ~70 |
| `codeinsight-frontend/src/app/__tests__/file-tree.test.tsx` | 文件树测试 | ~120 |
| `codeinsight-frontend/src/app/__tests__/structure-list.test.tsx` | 结构概览测试 | ~80 |
| `codeinsight-frontend/src/app/__tests__/status-badge.test.tsx` | 状态徽标测试 | ~40 |
| `codeinsight-frontend/src/app/__tests__/tree-utils.test.ts` | 树工具测试 | ~60 |
| `codeinsight-backend/tests/test_ast_node_api.py` | AST API 后端测试 | ~80 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `codeinsight-frontend/src/lib/api.ts` | 新增 AST 节点 API 路径常量 |
| `codeinsight-frontend/src/app/providers.tsx` | 可能更新 QueryClient 配置 |
| `codeinsight-backend/codeinsight/api/__init__.py` | 注册 ast_nodes 路由 |
| `codeinsight-backend/codeinsight/repositories/ast_node.py` | 新增 `get_by_file_id` 方法 |
| `codeinsight-frontend/package.json` | 可能需要新增依赖（如 lucide-react 图标） |

---

## 十四、任务完成状态

- [ ] 新增 AST 节点 API 路由（`/api/ast-nodes`）
- [ ] 修改 AstNodeDAO 新增 `get_by_file_id` 方法
- [ ] 编写 AST 节点 API 后端测试
- [ ] 创建 `packages/shared/src/constants.ts` 前端常量
- [ ] 创建 API 客户端（`api/files.ts`, `api/ast-nodes.ts`, `api/analysis.ts`）
- [ ] 创建数据钩子（`use-files.ts`, `use-ast-nodes.ts`, `use-analysis-status.ts`）
- [ ] 创建文件树组件（`FileTree/`）
- [ ] 创建结构概览组件（`Structure/`）
- [ ] 创建分析状态组件（`AnalysisStatus/`）
- [ ] 创建仓库详情布局（`[repo_id]/layout.tsx`）
- [ ] 创建文件树页面（`[repo_id]/files/page.tsx`）
- [ ] 实现 `buildFileTree` 工具函数
- [ ] 编写前端组件测试（20+ 用例）
- [ ] 端到端验证：打开仓库详情 → 查看文件树 → 点击文件 → 查看结构概览
- [ ] Vitest 全部通过
- [ ] ESLint 全部通过

---

## 总结

P2-07 是前端第一个核心数据页面，将后端的文件扫描和 AST 解析结果以可视化的方式呈现给用户。核心交付物：

1. **文件树** — 递归目录结构，可折叠/展开，支持选中
2. **结构概览** — 文件内函数/类/方法的层次化展示
3. **分析状态** — 实时显示仓库分析进度
4. **AST 节点 API** — 后端新增端点支持前端查询
5. **数据钩子** — TanStack Query 封装的 React hooks

该任务为 Phase 4（知识卡片、代码链路查看器）提供组件和数据流基础，是连接后端分析能力与前端用户交互的关键桥梁。

---

**开发日期**: 2026-07-14  
**开发人员**: Trae AI  
**任务编号**: P2-07  
**状态**: ⬜ 待实现
