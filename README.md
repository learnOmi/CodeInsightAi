# CodeInsight AI

> AI 驱动的代码知识提取与可视化分析平台

## 功能特性

- **代码仓库扫描**：支持指定本地目录，自动识别 Git 仓库
- **AST 结构解析**：Tree-sitter 支持 40+ 编程语言
- **AI 知识点提取**：LangGraph 多 Agent 协作分析
- **知识卡片展示**：前端交互式卡片列表
- **完整代码链路**：从入口到出口的调用链可视化
- **全文搜索**：Meilisearch 即时搜索 + pgvector 语义搜索
- **增量分析**：代码变更时只重新分析受影响部分
- **版本管理**：支持历史版本查看和回滚

## 快速开始

### 前置要求

- Python 3.12+
- Node.js 22+
- Docker & Docker Compose

### 安装

#### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆仓库
git clone <repo-url>
cd CodeInsightAi

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际值（特别是 SECRET_KEY）

# 3. 启动所有服务
docker compose up -d

# 4. 访问服务
# 前端: http://localhost:3000
# 后端 API: http://localhost:8000
# Meilisearch: http://localhost:7700
```

#### 方式二：本地开发

```bash
# 1. 克隆仓库
git clone <repo-url>
cd CodeInsightAi

# 2. 安装前端依赖
cd codeinsight-frontend && npm install && cd ..

# 3. 安装后端依赖
cd codeinsight-backend && uv sync && cd ..

# 4. 启动基础设施（PostgreSQL, Redis, Meilisearch）
docker compose up -d postgres redis meilisearch

# 5. 配置环境变量
cp codeinsight-backend/.env.example codeinsight-backend/.env
# 编辑 .env 填入实际值

# 6. 运行开发服务器
npm run dev
```

### 项目结构

```
CodeInsightAi/
├── codeinsight-backend/    # Python FastAPI 后端
│   ├── codeinsight/        # 应用代码
│   │   ├── api/            # API 路由
│   │   ├── models/         # 数据库模型
│   │   ├── services/       # 业务逻辑
│   │   ├── engines/        # 核心引擎
│   │   ├── agents/         # AI Agent
│   │   └── llm/            # LLM 客户端
│   ├── tasks/              # Celery 任务
│   └── tests/              # 测试
├── codeinsight-frontend/   # Next.js 前端
│   └── src/app/            # App Router 页面
├── packages/shared/        # 共享类型定义
│   └── src/
│       ├── repository.ts
│       ├── knowledge.ts
│       ├── analysis.ts
│       └── search.ts
├── .github/workflows/      # CI/CD
├── package.json            # Monorepo 根配置
└── dev-report/             # 开发报告
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 15, TypeScript, Tailwind CSS, Shiki, Zustand |
| 后端 | Python 3.12+, FastAPI, SQLAlchemy 2.0, Celery |
| AI | LangGraph, Claude/GPT-4o, Ollama, LiteLLM |
| 代码解析 | Tree-sitter, GitPython |
| 数据库 | PostgreSQL 16 + pgvector, Redis 7, Meilisearch |
| 基础设施 | Docker Compose, GitHub Actions |

## 开发规范

详见 [DEVELOPMENT-STANDARDS.md](code-analysis-dev-roadmap/DEVELOPMENT-STANDARDS.md)

## 许可证

MIT
