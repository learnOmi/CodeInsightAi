# P1-12: 共享 TypeScript/Python 类型定义 - 开发报告

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P1-12 |
| 任务名称 | 共享 TypeScript/Python 类型定义（KnowledgePoint, Repository 等） |
| 所属阶段 | Phase 1（第 2-3 周） |
| 优先级 | P1 |
| 预估工时 | 4h |
| 交付物 | `@codeinsight/shared` 包 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-03 Pydantic Schema | ✅ | Repository/AnalysisTask/KnowledgePoint 等已定义 |
| P1-11 OpenAPI 导出 | ✅ | `export_openapi.py` 脚本已就绪 |
| P1-09 前端框架 | ✅ | 前端已使用 `@codeinsight/shared` 类型 |

---

## 二、包结构

```
packages/shared/
├── package.json           # npm 包配置
├── tsconfig.json          # TypeScript 配置
└── src/
    ├── index.ts           # 类型导出入口
    ├── generated.ts       # 从 OpenAPI 自动生成的类型
    ├── openapi.json       # 从 FastAPI 导出的 OpenAPI schema
    └── constants.ts       # 前端专属常量（分类名称/颜色映射）
```

### 2.1 包配置

[package.json](file:///c:/Users/Administrator/CodeInsightAi/packages/shared/package.json)：

```json
{
  "name": "@codeinsight/shared",
  "version": "0.1.0",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "typecheck": "tsc --noEmit",
    "clean": "rm -rf dist"
  }
}
```

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `name` | `@codeinsight/shared` | 作用域包名 |
| `private` | `true` | 不发布到 npm，仅内部使用 |
| `main` | `dist/index.js` | CommonJS 入口 |
| `types` | `dist/index.d.ts` | TypeScript 声明入口 |

### 2.2 导出结构

[index.ts](file:///c:/Users/Administrator/CodeInsightAi/packages/shared/src/index.ts)：

```typescript
// 自动生成的类型（从后端 OpenAPI schema）
export type { paths, components, operations } from './generated';

// 前端专属常量
export { KNOWLEDGE_CATEGORY_NAMES, KNOWLEDGE_CATEGORY_COLORS } from './constants';
```

- `paths`: 所有 API 路径的 TypeScript 类型
- `components`: 所有 Schema 的 TypeScript 类型（`Repository`, `AnalysisTask` 等）
- `operations`: 所有 API 操作的 TypeScript 类型
- `KNOWLEDGE_CATEGORY_NAMES`: 分类显示名称映射
- `KNOWLEDGE_CATEGORY_COLORS`: 分类颜色映射

### 2.3 前端专属常量

[constants.ts](file:///c:/Users/Administrator/CodeInsightAi/packages/shared/src/constants.ts)：

| 常量 | 类型 | 说明 |
|------|------|------|
| `KNOWLEDGE_CATEGORY_NAMES` | `Record<KnowledgeCategory, string>` | 分类代码 → 中文名称 |
| `KNOWLEDGE_CATEGORY_COLORS` | `Record<KnowledgeCategory, string>` | 分类代码 → 颜色 hex |

使用 `generated.ts` 中的 `KnowledgeCategory` 类型确保类型安全。

---

## 三、类型同步机制

### 3.1 工作流程

```
后端 Pydantic Schema (Python)
    ↓
app.openapi() → openapi.json
    ↓
npx openapi-typescript packages/shared/src/openapi.json -o packages/shared/src/generated.ts
    ↓
前端 import type { Repository } from "@codeinsight/shared"
```

### 3.2 同步命令

```bash
# 1. 从后端导出 OpenAPI schema
cd codeinsight-backend && uv run python scripts/export_openapi.py

# 2. 生成 TypeScript 类型
npx openapi-typescript packages/shared/src/openapi.json -o packages/shared/src/generated.ts
```

或一键运行（如在根目录配置了 `npm run gen:types`）：

```bash
npm run gen:types
```

### 3.3 当前导出统计

| 指标 | 值 |
|------|-----|
| API 路径数 | 14 |
| Schema 数 | 29 |
| 包含模型 | Repository, RepositoryCreate, AnalysisTask, AnalysisVersion, KnowledgePoint, File 等 |

---

## 四、前端使用方式

### 4.1 基础用法

```typescript
import type { components } from '@codeinsight/shared';

type Repository = components['schemas']['Repository'];
type RepositoryCreate = components['schemas']['RepositoryCreate'];
type AnalysisTask = components['schemas']['AnalysisTask'];
```

### 4.2 API 操作类型

```typescript
import type { operations } from '@codeinsight/shared';

type ListRepositories = operations['list_repositories_api_v1_repositories_get'];
```

### 4.3 前端常量

```typescript
import { KNOWLEDGE_CATEGORY_NAMES, KNOWLEDGE_CATEGORY_COLORS } from '@codeinsight/shared';

const categoryName = KNOWLEDGE_CATEGORY_NAMES['DP-'];  // "设计模式"
const color = KNOWLEDGE_CATEGORY_COLORS['DP-'];  // "#3b82f6"
```

---

## 五、设计决策

### 5.1 为什么使用 OpenAPI 自动生成？

| 方案 | 优点 | 缺点 |
|------|------|------|
| **手写 TypeScript 类型** | 完全可控 | 容易与后端脱节，维护成本高 |
| **OpenAPI 自动生成** | 单一事实来源，类型始终一致 | 生成代码格式可能需调整 |

选择自动生成的原因是：**后端 Pydantic Schema 是单一事实来源**，前端类型必须与后端保持 100% 一致。

### 5.2 为什么分离 constants.ts？

`generated.ts` 是自动生成的，每次类型同步都会覆盖。前端专属常量（如显示名称、颜色）不应放在自动生成文件中，因此单独维护 `constants.ts`。

### 5.3 为什么包名带 `@codeinsight` 作用域？

| 方案 | 说明 |
|------|------|
| `shared`（裸包名） | 可能与第三方包冲突 |
| `@codeinsight/shared` | 明确归属，避免冲突，支持私有 npm registry |

---

## 六、验证结果

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 包构建 | ✅ | `tsc` 无错误 |
| 类型导出 | ✅ | `index.ts` 正确导出 |
| 前端使用 | ✅ | P1-09 前端已完整使用 |
| OpenAPI 同步 | ✅ | 29 个 Schema，14 个路径 |

---

## 七、总结

P1-12 任务已完成。`@codeinsight/shared` 包实现了**前后端类型自动化同步**，以 Pydantic Schema 为单一事实来源，通过 OpenAPI 导出 + `openapi-typescript` 生成工具链，确保前端类型与后端始终保持一致。前端通过 `import type { components } from "@codeinsight/shared"` 使用类型，避免了手写类型的维护成本。
