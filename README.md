# CodeInsight AI

> AI 驱动的代码知识提取与可视化分析平台

![Project Architecture](doc/code-analysis-dev-roadmap/architecture-overview.png)

CodeInsight AI 是一个全栈的智能代码分析平台，利用大语言模型（LLM）和图神经网络技术，从代码仓库中自动提取结构化知识、构建 AST 树、生成调用关系图，并提供强大的搜索与分析功能。

## 🚀 快速开始

### 前置要求

| 工具 | 版本 |
|------|------|
| Python | 3.12+ |
| Node.js | 18+ / 20+ (推荐 LTS) |
| npm | 9+ |
| Docker | 24+ (用于依赖服务) |
| PostgreSQL | 16+ |
| Redis | 7+ |
| Meilisearch | 0.30+ |

### 一键启动（Docker Compose）

```bash
# 克隆仓库
git clone <repo-url>
cd CodeInsightAi

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 SECRET_KEY、数据库密码等生产配置

# 启动所有基础设施服务
docker compose up -d postgres redis meilisearch

# 初始化数据库并运行迁移
cd codeinsight-backend && uv run alembic upgrade head && cd ..

# 启动前端和后端开发服务器
npm run dev
```

访问：http://localhost:3000

### 本地开发模式

```bash
# 1. 安装依赖
npm install

# 2. 安装后端依赖
cd codeinsight-backend
uv sync

# 3. 配置后端环境
cp .env.example .env
# 编辑 .env 填入 LLM API Key、数据库连接等信息

# 4. 运行后端
uv run uvicorn codeinsight.main:app --reload --host 0.0.0.0 --port 8000

# 5. 在另一个终端运行前端
cd codeinsight-frontend
npm run dev
```

---

## 🔍 核心功能

### 1. 仓库管理
- 导入本地 Git 仓库或远程仓库路径
- 自动识别分支、提交历史和文件结构
- 支持多仓库并发分析

### 2. 智能分析引擎
| 功能 | 技术实现 |
|------|---------|
| **AST 解析** | Tree-sitter (支持 Python, JS/TS, Java, Go, Rust 等 40+ 语言) |
| **代码扫描** | GitPython + Tree-sitter 增量扫描 |
| **调用图构建** | 自定义图算法，解析函数/方法调用关系 |
| **模块依赖分析** | 静态分析 import/require 语句 |
| **框架检测** | 识别项目中使用的 Web 框架、库和中间件 |

### 3. AI 知识提取
基于 LangGraph 的多 Agent 协作流水线：
- **规划 Agent**：制定分析策略和步骤
- **解析 Agent**：提取 AST 节点和语义信息
- **推理 Agent**：结合上下文进行深度分析
- **综合 Agent**：聚合所有结果生成结构化知识卡片

### 4. 可视化展示
- **交互式调用图**：使用 XFlow 节点图展示函数调用关系
- **AST 树视图**：语法树的分层折叠展示
- **知识卡片网格**：自动标记的关键概念、类和方法
- **依赖关系图谱**：模块间依赖关系的环形图

### 5. 高级搜索
- **全文搜索**：Meilisearch 实时检索代码和历史分析结果
- **语义搜索**：基于 pgvector 的向量相似度匹配
- **组合查询**：支持条件过滤和排序

### 6. 增量分析
- 自动检测代码变更
- 仅重新分析受影响的文件和模块
- 支持回溯到历史快照版本

### 7. 版本控制
- 每次分析保存为独立快照
- 可对比不同版本的差异
- 支持版本回滚和数据恢复

---

## 📦 技术栈

### 前端 (Next.js 15)
- **框架**：Next.js 15 App Router
- **样式**：Tailwind CSS 4
- **状态管理**：Zustand
- **数据获取**：React Query
- **流程图库**：XFlow
- **代码高亮**：Shiki
- **图标库**：lucide-react
- **动画**：Framer Motion

### 后端 (Python 3.12+)
- **Web 框架**：FastAPI
- **异步任务**：Celery + Redis
- **ORM**：SQLAlchemy 2.0 (Async)
- **Agent 编排**：LangGraph
- **代码解析**：Tree-sitter
- **搜索**：Meilisearch (全文) + pgvector (向量)
- **认证**：JWT / API Key

### AI & LLM
| 组件 | 用途 |
|------|------|
| LangChain/LangGraph | Agent 工作流编排 |
| LiteLLM | 统一多模型接口 (OpenAI, Anthropic, Ollama) |
| Sentence Transformers | 文本向量化嵌入 |
| pgvector | 向量存储与相似度搜索 |

### 基础设施
| 服务 | 端口 | 用途 |
|------|------|------|
| PostgreSQL | 5432 | 关系型数据存储 + pgvector |
| Redis | 6379 | Celery 任务队列 + 缓存 |
| Meilisearch | 7700 | 全文搜索引擎 |
| Celery Worker | - | 异步任务处理 |
| FastAPI | 8000 | REST API 服务 |
| Next.js | 3000 | 前端应用 |

---

## 🏗️ 项目结构

```
CodeInsightAi/
├── codeinsight-backend/               # Python FastAPI 后端服务
│   ├── codeinsight/                   # 主应用包
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI 应用入口
│   │   ├── config.py                  # 配置管理（Pydantic Settings）
│   │   ├── exceptions.py              # 自定义异常
│   │   ├── dependencies.py            # DI 依赖注入
│   │   ├── api/                       # API 路由模块
│   │   │   ├── repositories.py        # 仓库管理
│   │   │   ├── analysis.py            # 分析任务
│   │   │   ├── knowledge.py           # 知识点
│   │   │   ├── search.py              # 搜索
│   │   │   ├── ast_nodes.py           # AST 节点
│   │   │   ├── call_edges.py          # 调用边
│   │   │   └── ...                    # 共 14 个 API 端点
│   │   ├── models/                    # SQLAlchemy 模型
│   │   ├── schemas/                   # Pydantic Schema
│   │   ├── services/                  # 业务服务
│   │   │   ├── llm/                   # LLM 客户端
│   │   │   ├── scanners/              # 代码扫描器
│   │   │   ├── parsers/               # 解析器
│   │   │   ├── engines/               # 核心引擎
│   │   │   │   ├── call_graph.py      # 调用图生成
│   │   │   │   ├── module_graph.py    # 模块依赖图
│   │   │   │   └── framework_detector.py
│   │   │   └── services.py
│   │   ├── agents/                    # AI Agent (LangGraph)
│   │   │   ├── planning_agent.py
│   │   │   ├── parsing_agent.py
│   │   │   ├── reasoning_agent.py
│   │   │   └── synthesis_agent.py
│   │   ├── tasks/                     # Celery 任务
│   │   │   ├── analysis_tasks.py
│   │   │   └── __init__.py
│   │   ├── pipelines/                 # 分析流水线
│   │   ├── evaluation/                # 评估框架
│   │   ├── db/                        # 数据库会话
│   │   ├── embedding/                 # 向量化
│   │   └── utils/                     # 工具函数
│   ├── alembic/                       # 数据库迁移 (含多个版本迁移文件)
│   ├── tests/                         # pytest 测试套件 (>30 个测试文件)
│   │   ├── test_*.py
│   │   └── conftest.py
│   ├── scripts/                       # 辅助脚本
│   │   ├── export_openapi.py          # 导出 OpenAPI 规范供前端同步类型
│   │   └── seed_test_data.py          # 测试数据填充
│   ├── pyproject.toml                 # 依赖管理 (Uv/Poetry)
│   └── README.md
│
├── codeinsight-frontend/              # Next.js 前端应用
│   ├── app/                           # App Router 页面
│   │   ├── page.tsx                   # 首页
│   │   ├── layout.tsx               # 全局布局
│   │   └── components/              # UI 组件
│   ├── src/                           # 源代码
│   │   ├── lib/                     # 工具库
│   │   ├── types/                   # TypeScript 类型
│   │   └── store/                   # Zustand 状态管理
│   ├── next.config.ts                 # Next.js 配置
│   ├── tsconfig.json                  # TypeScript 配置
│   ├── package.json                   # 前端依赖
│   └── tailwind.config.ts             # Tailwind 配置
│
├── packages/shared/                   # 共享类型定义 (TypeScript)
│   ├── src/
│   │   ├── repository.ts            # 仓库类型
│   │   ├── knowledge.ts             # 知识类型
│   │   ├── analysis.ts              # 分析类型
│   │   ├── search.ts                # 搜索类型
│   │   └── generated.ts             # 自动生成自 OpenAPI
│   ├── tsconfig.json
│   └── package.json
│
├── doc/                               # 开发文档
│   ├── code-analysis-dev-roadmap/   # 开发路线图文档
│   │   ├── BUSINESS-FLOW-DIAGRAM.md
│   │   ├── DEVELOPMENT-STANDARDS.md
│   │   ├── API-REFERENCE.md
│   │   └── CODEINSIGHT-AI-DEVELOPMENT-PLAN.md
│   └── dev-analysis/                # 功能分析报告
│       ├── comprehensive-functionality-analysis.md
│       └── ...
│
├── dev-report/                        # 开发过程报告 (P1-P3 阶段)
│   ├── P1-*.md                      # 第一阶段完成报告
│   ├── P2-*.md                      # 第二阶段增强报告
│   └── ...
│
├── .env.example                       # 环境变量模板 (含详细注释)
├ .gitignore                           # Git 忽略规则
├ docker-compose.yml                   # 服务编排 (postgres, redis, meilisearch)
├ package.json                         # 根 package (工作空间管理 + Conforrrently)
├ README.md                            # 本文档
└ scripts/                             # 根级脚本
    ├── cleanup.ps1                  # 清理脚本
    ├── evaluate.py                  # 性能评估
    └── validate_eval_data.py        # 数据验证
```

---

## 🧪 测试与质量保证

### 测试命令

```bash
# 运行全部测试
npm run test

# 仅后端测试
cd codeinsight-backend && pytest

# 仅前端测试
cd codeinsight-frontend && npm test

# 带覆盖率报告
pytest --cov=codeinsight --cov-report=html

# 运行 linter
npm run lint

# 格式化代码
npm run format
```

### 代码质量检查

| 工具 | 配置 |
|------|------|
| Ruff | 代码 linting (fast)，行宽 120，目标 Python 3.12 |
| Mypy | 静态类型检查，启用严格的类型检查规则 |
| ESLint | 前端 TypeScript 检查，集成 Next.js 插件 |
| Prettier | 代码格式化 |

---

## 🤝 贡献指南

欢迎贡献！请阅读 [DEVELOPMENT-STANDARDS.md](doc/code-analysis-dev-roadmap/DEVELOPMENT-STANDARDS.md) 了解代码规范和开发流程。

### 开发工作流

```bash
# 1. 创建特性分支
git checkout -b feat/new-feature

# 2. 开发和提交
git add .
git commit -m "feat: implement new feature"

# 3. 推送并创建 PR
git push origin feat/new-feature

# 4. 运行 CI 测试
# 确保所有检查通过后合并
```

---

## 📄 许可证

MIT © [您的组织名称](https://github.com/your-org)

## 🙌 致谢

- 感谢 [LangChain](https://langchain.ai/) 和 [LangGraph](https://langchain-langgraph.github.io/langgraph/) 提供强大的 Agent 编排框架
- 感谢 [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) 提供跨语言的语法解析能力
- 感谢 [Meilisearch](https://meilisearch.com/) 提供快速的全文搜索
- 感谢 [FastAPI](https://fastapi.tiangolo.com/) 提供现代化的 Python Web 框架
