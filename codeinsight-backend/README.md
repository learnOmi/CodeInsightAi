# CodeInsight AI 后端服务

FastAPI + SQLAlchemy + Celery + LangGraph 后端服务。

## 快速开始

```bash
# 安装依赖
cd codeinsight-backend
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入数据库等信息

# 运行开发服务器
uv run uvicorn codeinsight.main:app --reload
```

## 项目结构

```
codeinsight-backend/
├── codeinsight/
│   ├── main.py          # FastAPI 应用入口
│   ├── config.py        # 配置管理
│   ├── dependencies.py  # DI 依赖注入
│   ├── api/             # API 路由
│   ├── models/          # 数据库模型
│   ├── schemas/         # Pydantic Schema
│   ├── services/        # 业务逻辑
│   ├── engines/         # 核心引擎（扫描/解析/调用图）
│   ├── agents/          # AI Agent
│   ├── llm/             # LLM 客户端
│   └── utils/           # 工具函数
├── tasks/               # Celery 任务
├── alembic/             # 数据库迁移
├── tests/               # 测试
└── pyproject.toml
```
