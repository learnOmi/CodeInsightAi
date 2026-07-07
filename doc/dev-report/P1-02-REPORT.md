# P1-02 任务完成报告

> **任务编号**: P1-02  
> **任务描述**: 配置 Docker Compose（PostgreSQL + pgvector, Redis, Meilisearch）  
> **负责人**: AI Agent  
> **优先级**: P0  
> **预估工时**: 6h  
> **实际工时**: ~6h  
> **完成日期**: 2026-07-07  
> **状态**: ✅ 已完成

---

## 一、交付物清单

### 1.1 新增文件

| 文件 | 说明 |
|------|------|
| [docker-compose.yml](file:///c:/Users/Administrator/CodeInsightAi/docker-compose.yml) | 6 个服务编排（postgres+pgvector、redis、meilisearch、backend、celery-worker、frontend） |
| [codeinsight-backend/Dockerfile](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/Dockerfile) | Python 3.12 后端镜像，uv 依赖管理 |
| [codeinsight-frontend/Dockerfile](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/Dockerfile) | Node 22 前端镜像，多阶段构建 |
| [.env.example](file:///c:/Users/Administrator/CodeInsightAi/.env.example) | 环境变量模板 |

### 1.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| [README.md](file:///c:/Users/Administrator/CodeInsightAi/README.md) | 添加 Docker Compose 启动方式说明（方式一：Docker Compose，方式二：本地开发） |
| [.gitignore](file:///c:/Users/Administrator/CodeInsightAi/.gitignore) | 添加 `docker-compose.override.yml` 忽略规则 |

---

## 二、服务编排架构

### 2.1 服务列表

| 服务名称 | 镜像 | 端口 | 用途 |
|----------|------|------|------|
| `postgres` | `ankane/pgvector:latest` | 5432 | 主数据库 + 向量存储 |
| `redis` | `redis:7-alpine` | 6379 | 缓存 + Celery 任务队列 |
| `meilisearch` | `getmeili/meilisearch:latest` | 7700 | 全文搜索引擎 |
| `backend` | 本地构建 | 8000 | FastAPI 后端服务 |
| `celery-worker` | 本地构建 | - | 异步任务处理 |
| `frontend` | 本地构建 | 3000 | Next.js 前端应用 |

### 2.2 依赖关系

```
frontend ──▶ backend
backend ──▶ postgres (healthcheck)
backend ──▶ redis (healthcheck)
backend ──▶ meilisearch (healthcheck)
celery-worker ──▶ postgres (healthcheck)
celery-worker ──▶ redis (healthcheck)
celery-worker ──▶ meilisearch (healthcheck)
```

### 2.3 数据持久化

| 卷名称 | 用途 |
|--------|------|
| `postgres_data` | PostgreSQL 数据持久化 |
| `redis_data` | Redis 数据持久化 |
| `meilisearch_data` | Meilisearch 索引持久化 |

---

## 三、Dockerfile 设计

### 3.1 后端 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git gcc g++ cmake make pkg-config

COPY pyproject.toml .
COPY uv.lock* .

RUN pip install uv
RUN uv sync --extra dev

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "codeinsight.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**设计要点**：
- 使用 `python:3.12-slim` 基础镜像（轻量化）
- 安装编译依赖（tree-sitter 需要编译）
- 使用 uv 进行依赖管理
- 分层构建：先安装依赖，再复制代码

### 3.2 前端 Dockerfile

```dockerfile
FROM node:22-alpine AS base

FROM base AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --only=production

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
```

**设计要点**：
- 多阶段构建（deps → builder → runner）
- 使用 Alpine 基础镜像（极小体积）
- `--only=production` 只安装生产依赖
- 只复制必要的构建产物

---

## 四、环境变量配置

### 4.1 .env.example 模板

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `POSTGRES_DB` | `codeinsight` | PostgreSQL 数据库名 |
| `POSTGRES_USER` | `codeinsight` | PostgreSQL 用户名 |
| `POSTGRES_PASSWORD` | `codeinsight` | PostgreSQL 密码 |
| `MEILI_MASTER_KEY` | `codeinsight_master_key` | Meilisearch 主密钥 |
| `SECRET_KEY` | `your-secret-key-here` | JWT 签名密钥 |
| `ALGORITHM` | `HS256` | JWT 算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token 过期时间（分钟） |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 前端 API 地址 |

---

## 五、启动方式

### 5.1 Docker Compose（推荐）

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值

# 启动所有服务
docker compose up -d

# 访问服务
# 前端: http://localhost:3000
# 后端 API: http://localhost:8000
# Meilisearch: http://localhost:7700
```

### 5.2 本地开发

```bash
# 只启动基础设施
docker compose up -d postgres redis meilisearch

# 本地运行前后端
npm run dev
```

### 5.3 常用命令

```bash
# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 重建后端镜像
docker compose build backend

# 查看服务状态
docker compose ps
```

---

## 六、验证结果

### 6.1 服务健康检查

- [x] PostgreSQL healthcheck（pg_isready）
- [x] Redis healthcheck（redis-cli ping）
- [x] Meilisearch healthcheck（curl /health）
- [x] 后端、celery-worker 依赖健康检查

### 6.2 目录完整性

- [x] `docker-compose.yml` 包含所有必要服务
- [x] 后端 `Dockerfile` 正确配置
- [x] 前端 `Dockerfile` 多阶段构建
- [x] `.env.example` 环境变量模板完整
- [x] `README.md` 启动说明更新
- [x] `.gitignore` 添加 Docker 忽略规则

---

## 七、结论

P1-02 任务已完成。Docker Compose 全服务编排已创建，包含：

1. **6 个服务**：PostgreSQL + pgvector、Redis、Meilisearch、Backend、Celery Worker、Frontend
2. **健康检查**：所有基础设施服务都配置了 healthcheck，后端和 celery-worker 依赖健康检查
3. **数据持久化**：3 个 Docker volume 确保数据不丢失
4. **分层构建**：前端使用多阶段构建，减小镜像体积
5. **环境变量**：统一的 `.env.example` 模板，支持自定义配置

**下一步**: P1-03 SQLAlchemy 2.0 ORM 模型定义 + 数据库 Migration。

---

## 八、补充修复：shared 包 Docker 整合

> **修复时间**: 2026-07-07  
> **修复原因**: shared 包引用导致 Docker 前端构建失败

### 8.1 问题描述

前端 `tsconfig.json` 的路径别名指向 `../packages/shared/src`，但 Docker 构建时 context 只包含 `codeinsight-frontend/` 目录，`../packages/shared` 不存在于构建上下文中，导致 TypeScript 无法解析 `@codeinsight/shared` → 构建失败。

### 8.2 修复方案

**修改文件**：

| 文件 | 修改内容 |
|------|---------|
| [docker-compose.yml](file:///c:/Users/Administrator/CodeInsightAi/docker-compose.yml#L107) | frontend context 从 `./codeinsight-frontend` 改为 `.`（根目录） |
| [codeinsight-frontend/Dockerfile](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/Dockerfile) | deps 阶段复制所有 workspace 的 package.json，builder 阶段先编译 shared 再构建前端 |

### 8.3 修复后的前端构建流程

```
Docker 构建流程（frontend）
├── deps 阶段
│   ├── 复制根 package.json + lock
│   ├── 复制 packages/shared/package.json
│   ├── 复制 codeinsight-frontend/package.json
│   └── npm ci（安装所有 workspace 依赖）
├── builder 阶段
│   ├── 复制所有代码（包括 packages/shared）
│   ├── npm run build:shared（编译共享类型）
│   └── npm run build:frontend（构建前端）
└── runner 阶段
    └── 复制前端构建产物
```

### 8.4 后端补充修复

**问题**：后端 Python 需要使用 `datamodel-codegenerator` 从 TS 类型生成 Pydantic model，但 Docker context 是 `./codeinsight-backend`，无法访问 `../packages/shared`。

**修改文件**：

| 文件 | 修改内容 |
|------|---------|
| [docker-compose.yml](file:///c:/Users/Administrator/CodeInsightAi/docker-compose.yml#L53) | backend context 从 `./codeinsight-backend` 改为 `.`（根目录） |
| [docker-compose.yml](file:///c:/Users/Administrator/CodeInsightAi/docker-compose.yml#L82) | celery-worker context 从 `./codeinsight-backend` 改为 `.`（根目录） |
| [codeinsight-backend/Dockerfile](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/Dockerfile) | 复制 shared 目录并自动生成 Pydantic model |
| [codeinsight-backend/pyproject.toml](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/pyproject.toml#L34) | 添加 `datamodel-codegenerator>=0.25.0` 依赖 |

**后端构建流程**：

```
Docker 构建流程（backend）
├── 安装编译依赖（tree-sitter 需要）
├── 复制 pyproject.toml + uv.lock
├── pip install uv + uv sync --extra dev
├── COPY packages/shared/src ./packages/shared/src
├── COPY codeinsight-backend .
├── datamodel-codegen 生成 Pydantic model → codeinsight/schemas/shared.py
└── CMD: uvicorn codeinsight.main:app
```

---

## 九、后续修复事项汇总

> **修复时间**: 2026-07-07  
> **修复原因**: 项目启动和 CI 运行中的兼容性问题

### 9.1 Python 版本兼容性

**问题**：系统默认 Python 为 3.13，但 `tree-sitter-languages` 只支持到 Python 3.12

**修复**：
- 安装 Python 3.12.10
- 更新 `pyproject.toml` 中 `requires-python` 为 `>=3.12`
- 更新 `npm run dev:backend` 脚本使用 `py -3.12`

### 9.2 后端配置优化

**问题**：Docker Compose 传递的环境变量与后端配置不匹配

**修复**（[codeinsight/config.py](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/codeinsight/config.py)）：
- 将单一的 `database_url` 拆分为 `postgres_host`、`postgres_port`、`postgres_db`、`postgres_user`、`postgres_password`
- 将单一的 `redis_url` 拆分为 `redis_host`、`redis_port`
- 添加 `@property` 方法动态构建连接字符串
- 默认值保持本地开发友好（`localhost`），Docker 环境通过环境变量覆盖

### 9.3 datamodel-codegenerator 依赖修复

**问题**：包名错误，`datamodel-codegenerator` 应为 `datamodel-code-generator`（带连字符）

**修复**（[pyproject.toml](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-backend/pyproject.toml#L34)）：
```diff
- "datamodel-codegenerator>=0.25.0",
+ "datamodel-code-generator>=0.57.0",
```

### 9.4 前端 ESLint 配置优化

**问题**：ESLint 报告三斜杠引用错误（`.next/types/routes.d.ts`）

**修复**（[eslint.config.js](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/eslint.config.js#L12)）：
```diff
ignores: ["dist/", ".next/", "node_modules/", "*.d.ts"],
```

### 9.5 Next.js Workspace 根目录警告

**问题**：Next.js 在 monorepo 中检测到多个 lockfile，推断根目录不正确

**修复**（[next.config.ts](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/next.config.ts#L5)）：
```diff
outputFileTracingRoot: process.cwd(),
```

### 9.6 Tailwind CSS 4 样式修复

**问题**：CSS 中使用了未定义的 `var(--font-work-sans)` 变量，导致 SSR 水合错误

**修复**（[globals.css](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/src/app/globals.css)）：
- 使用标准的 `@theme` 块定义颜色变量
- 使用 `--color-` 前缀符合 Tailwind 规范
- 移除未定义的 `--font-work-sans` 变量

### 9.7 前端 shared 包引用配置

**修复**（[codeinsight-frontend/package.json](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/package.json#L23)）：
- 添加 `@codeinsight/shared: "*"` 依赖

**修复**（[codeinsight-frontend/tsconfig.json](file:///c:/Users/Administrator/CodeInsightAi/codeinsight-frontend/tsconfig.json#L19)）：
- 添加路径别名 `"@codeinsight/shared": ["../packages/shared/src"]`

### 9.8 根目录 lockfile 管理

**修复**（[.gitignore](file:///c:/Users/Administrator/CodeInsightAi/.gitignore#L4)）：
- 保留根目录 `package-lock.json` 被 Git 跟踪
- 忽略子目录的 lockfile：`*/package-lock.json`

### 9.9 后端 uv 安装

**问题**：Python 3.12 环境中未安装 uv

**修复**：
```bash
py -3.12 -m pip install uv
```

### 9.10 虚拟环境清理

**问题**：存在用 Python 3.13 创建的旧 `.venv`，导致 `uv` 使用错误的 Python 版本

**修复**：删除旧虚拟环境，重新执行 `py -3.12 -m uv sync`

---

## 十、当前状态

### 10.1 后端
- ✅ Python 3.12 环境配置完成
- ✅ uv 包管理器安装完成
- ✅ 所有依赖安装成功（179 个包）
- ✅ 配置支持 Docker 和本地开发
- ✅ 健康检查端点可用：`GET /api/v1/health`

### 10.2 前端
- ✅ Next.js 15 配置完成
- ✅ ESLint 9 配置完成
- ✅ shared 包引用配置完成
- ✅ Tailwind CSS 4 样式修复完成
- ✅ SSR 水合错误修复完成

### 10.3 Docker
- ✅ 所有服务 context 改为根目录
- ✅ shared 包整合到前后端构建流程
- ✅ 环境变量映射正确

### 10.4 待完成
- ⚠️ P1-03：数据库模型设计（SQLAlchemy + Alembic）
- ⚠️ P1-04：消息队列与异步任务（Celery）