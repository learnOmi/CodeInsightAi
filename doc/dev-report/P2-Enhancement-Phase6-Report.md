# Phase 6 完成报告：前端展示

## 一、概述

Phase 6 实现了分析结果的前端可视化展示，将 Phase 4/5 后端产生的框架检测、API 路由、外部依赖、中间件链等数据以直观的 UI 组件呈现给用户。

### 完成情况
- **计划任务数**：5 项
- **完成任务数**：5 项
- **完成率**：100%

---

## 二、交付物清单

### 2.1 新增文件

| 文件路径 | 功能说明 |
|---------|---------|
| `src/api/dependencies.ts` | 外部依赖 API 封装 |
| `src/api/routes.ts` | API 路由 API 封装 |
| `src/api/frameworks.ts` | 框架检测 API 封装 |
| `src/hooks/use-analysis-results.ts` | React Query hooks（依赖/路由/框架） |
| `src/components/common/FrameworkBadge.tsx` | 框架标签 chip 组件 |
| `src/components/analysis/RouteList.tsx` | API 路由列表（含过滤） |
| `src/components/analysis/DependencyList.tsx` | 外部依赖列表（按生态分组） |
| `src/components/analysis/FrameworkList.tsx` | 框架检测结果（卡片网格 + 置信度） |
| `src/components/analysis/MiddlewareChain.tsx` | 中间件链 DAG 可视化 |

### 2.2 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `src/api/index.ts` | 导出 dependencies、routes、frameworks 模块 |
| `src/components/structure/StructureList.tsx` | 集成 FrameworkBadge 显示框架标签 |
| `src/components/call-graph/CallGraph.tsx` | 新增 external/injected 调用类型样式 |
| `src/app/repositories/[repo_id]/files/page.tsx` | 新增 API 路由/外部依赖/框架检测 Tab |

---

## 三、核心功能详解

### 3.1 框架标签展示（FrameworkBadge）

在代码结构列表中，每个 AST 节点名称后显示框架标签 chip。

**配色规则**（按前缀匹配）：
- `react-*` → 蓝色
- `vue-*` → 绿色
- `angular-*` → 红色
- `http-controller` / `api-endpoint` → 紫色
- `business-service` / `data-repository` → 青色
- `flask-*` / `fastapi-*` → 橙色
- `express-*` / `koa-*` → 黄色
- `dependency-injection` / `transactional` / `scheduled-task` → 灰色

### 3.2 API 路由列表（RouteList）

**功能**：
- 展示所有 API 路由，每行显示 HTTP 方法标签、路径模式、处理函数、框架来源
- HTTP 方法颜色编码：GET=绿色、POST=蓝色、PUT=黄色、DELETE=红色、PATCH=紫色
- 中间件数量徽章（`MW: N`）
- 过滤功能：HTTP 方法下拉、框架下拉、路径搜索框
- 加载骨架屏 + 空状态处理

### 3.3 外部依赖列表（DependencyList）

**功能**：
- 按生态系统分组展示（Maven ☕ / NPM 📦 / Pip 🐍 / Go 🐹 / Cargo 🦀）
- 每个依赖显示包名、版本号/版本范围、作用域标签
- 作用域颜色编码：compile=蓝色、dev=黄色、test=绿色、peer=紫色
- 过滤功能：生态系统下拉、作用域下拉
- 加载/空/错误状态处理

### 3.4 调用图增强（CallGraph）

新增两种调用类型的视觉样式：
- **`external`**（外部依赖调用）：绿色虚线（`#10b981`, `3,3`）
- **`injected`**（依赖注入调用）：紫色点线（`#a855f7`, `1,2`）

新增 `external` 节点类型配置：
- 颜色：`#10b981`（绿色）
- 标签："外部"

### 3.5 中间件链可视化（MiddlewareChain）

**功能**：
- 水平排列的 DAG 布局展示中间件执行顺序
- 每个中间件卡片显示：类型徽标、序号、名称、文件路径
- 节点间用 SVG 箭头连接
- 中间件类型配色：authentication=红色、rate_limiting=橙色、logging=蓝色、cors=绿色
- 空状态显示"无中间件"
- 支持横向滚动

### 3.6 框架检测结果（FrameworkList）

**功能**：
- 卡片网格布局展示检测到的框架
- 每个卡片显示：框架名称、分类标签、置信度进度条、证据信息
- 置信度颜色：≥80%=绿色、≥50%=黄色、<50%=灰色
- 过滤功能：分类下拉、最低置信度下拉
- 框架名称友好显示映射（spring_boot → "Spring Boot"）

### 3.7 页面集成

文件页面新增三个 Tab：
- **API 路由**：仓库级路由列表，无需选中文件
- **外部依赖**：仓库级依赖列表，无需选中文件
- **框架检测**：仓库级框架检测结果，无需选中文件

原有 Tab（代码结构、调用图）需要选中文件后才显示内容。

---

## 四、技术架构

### 4.1 数据流

```
后端 API (FastAPI)
  ├── /api/v1/repositories/{id}/dependencies
  ├── /api/v1/repositories/{id}/routes
  └── /api/v1/repositories/{id}/frameworks
       │
       ▼
前端 API 层 (src/api/*.ts)
  ├── dependencies.ts  → getDependencies()
  ├── routes.ts        → getRoutes()
  └── frameworks.ts    → getFrameworks()
       │
       ▼
React Query Hooks (src/hooks/use-analysis-results.ts)
  ├── useDependencies()
  ├── useRoutes()
  └── useFrameworks()
       │
       ▼
UI 组件 (src/components/analysis/*.tsx)
  ├── DependencyList.tsx
  ├── RouteList.tsx
  ├── FrameworkList.tsx
  └── MiddlewareChain.tsx
```

### 4.2 设计模式

- **API 层**：与现有 `files.ts`、`repositories.ts` 一致的 `apiFetch<T>` 封装模式
- **Hooks 层**：React Query + `useQuery` 封装，2 分钟 staleTime 缓存
- **组件层**：自包含组件，内部管理过滤状态，通过 props 接收 `repositoryId`
- **样式**：TailwindCSS + CSS 变量（`var(--bg-card)` 等），适配明暗主题

---

## 五、验证结果

| 验证项 | 结果 |
|-------|------|
| TypeScript 编译 (`tsc --noEmit`) | ✅ 通过 |
| ESLint (`next lint`) | ✅ No ESLint warnings or errors |
| 现有功能兼容 | ✅ 无破坏性变更 |

---

## 六、已知限制与后续优化

### 6.1 已知限制
1. **类型定义手动维护**：Phase 5 的 TypeScript 类型未通过 OpenAPI 自动生成，手动定义在 API 文件中
2. **框架标签依赖后端 tags 字段**：当前 AstNode 的 generated 类型中无 tags 字段，通过可选读取方式兼容
3. **中间件链为简化 DAG**：使用 flex 布局而非真正的图布局算法

### 6.2 后续优化方向
1. 运行 `npm run gen:types` 自动生成 Phase 5 类型到 `generated.ts`
2. 添加调用图版本切换 UI（切换 analysis_version_id 查看不同版本的调用图）
3. 中间件链支持交互式展开/折叠
4. 框架检测支持按目录/模块分组查看
5. 外部依赖支持依赖树可视化（传递依赖关系）

---

## 七、总结

Phase 6 成功将后端分析结果以直观的 UI 组件呈现，覆盖了 P2 增强方案中全部 5 项前端展示任务。用户现在可以在文件页面中切换 Tab 查看框架检测、API 路由、外部依赖等分析结果，代码结构列表中也展示了框架标签。
