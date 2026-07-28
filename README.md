# CodeInsight AI

> AI-powered code knowledge extraction and visual analysis platform

![Project Architecture](doc/code-analysis-dev-roadmap/architecture-overview.png)

CodeInsight AI is a full-stack intelligent code analysis platform that leverages Large Language Models (LLM) and graph-based algorithms to automatically extract structured knowledge from code repositories, build AST trees, generate call graphs, and provide powerful search and analysis capabilities.

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12+ |
| Node.js | 18+ / 20+ (LTS recommended) |
| npm | 9+ |
| Docker | 24+ (for infrastructure services) |
| PostgreSQL | 16+ |
| Redis | 7+ |
| Meilisearch | 0.30+ |

### One-Click Start (Docker Compose)

```bash
# Clone the repository
git clone <repo-url>
cd CodeInsightAi

# Configure environment variables
cp .env.example .env
# Edit .env to set SECRET_KEY, database passwords, etc.

# Start all infrastructure services
docker compose up -d postgres redis meilisearch

# Initialize the database and run migrations
cd codeinsight-backend && uv run alembic upgrade head && cd ..

# Start frontend and backend development servers
npm run dev
```

Visit: http://localhost:3000

### Local Development Mode

```bash
# 1. Install dependencies
npm install

# 2. Install backend dependencies
cd codeinsight-backend
uv sync

# 3. Configure backend environment
cp .env.example .env
# Edit .env to set LLM API Key, database connection, etc.

# 4. Run the backend
uv run uvicorn codeinsight.main:app --reload --host 0.0.0.0 --port 8000

# 5. In another terminal, run the frontend
cd codeinsight-frontend
npm run dev
```

---

## 🔍 Core Features

### 1. Repository Management
- **Import repositories** — Clone local Git repositories or connect to remote repository paths
- **Multi-repository support** — Manage and analyze multiple repositories concurrently with status tracking
- **Automatic scanning** — Automatically identify branches, commit history, and file structures
- **Real-time progress** — SSE-based live progress tracking for analysis tasks with step-by-step status updates

### 2. Intelligent Analysis Engine

| Feature | Technology |
|---------|-----------|
| **AST Parsing** | Tree-sitter (supports 40+ languages including Python, JS/TS, Java, Go, Rust) |
| **Code Scanning** | GitPython + Tree-sitter incremental scanning |
| **Call Graph Construction** | Custom graph algorithms to resolve function/method call relationships |
| **Module Dependency Analysis** | Static analysis of import/require statements with interactive dependency graph |
| **Framework Detection** | Identify web frameworks, libraries, and middleware used in the project |
| **API Route Extraction** | Discover and catalog HTTP API endpoints and middleware chains |
| **Language Distribution** | Visual breakdown of languages used across the repository |

### 3. AI Knowledge Extraction

A multi-agent collaboration pipeline powered by LangGraph:

- **Planning Agent** — Formulates analysis strategies and step-by-step plans
- **Parsing Agent** — Extracts AST nodes, semantic information, and code structure
- **Reasoning Agent** — Performs deep contextual analysis, identifying design patterns, architectural decisions, and domain knowledge
- **Synthesis Agent** — Aggregates all results into structured, categorized knowledge cards

**Knowledge Categories**:
| Category | Description |
|----------|-------------|
| Design Patterns | Recognized GoF patterns, architectural patterns, and anti-patterns |
| Architecture Decisions | Key architectural choices, trade-offs, and rationale |
| Algorithm Implementations | Notable algorithms, data structures, and optimization techniques |
| Engineering Tips | Best practices, code idioms, and performance insights |
| Domain Knowledge | Business logic, domain rules, and specialized terminology |
| Development Templates | Boilerplate code, project scaffolding, and reusable patterns |
| Tech Stack | Detected technologies, libraries, and their versions |

### 4. Visual Analysis & Exploration

- **Interactive Call Graph** — XFlow-based node graph displaying function call relationships with expand/collapse and focus mode
- **AST Tree View** — Hierarchical syntax tree with collapsible nodes and detailed annotations
- **Knowledge Card Grid** — Auto-tagged cards for key concepts, classes, methods, and design insights
- **Module Dependency Graph** — Circular dependency visualization with import/export relationships
- **Code Structure Tree** — File-level and symbol-level structure browser with navigation
- **Call Chain Explorer** — Follow forward and backward call chains interactively through the graph

### 5. Advanced Search

- **Full-Text Search** — Meilisearch-powered real-time search across code and historical analysis results
- **Semantic Search** — pgvector-based vector similarity matching for intent-aware code lookup
- **Combined Queries** — Filter by repository, language, knowledge category, or analysis version
- **Knowledge Search** — Search across extracted knowledge cards with category filtering

### 6. Incremental Analysis

- Automatically detects code changes since the last analysis
- Re-analyzes only affected files and modules for efficiency
- Supports rollback to historical snapshot versions
- Parallel processing of independent analysis stages

### 7. Version Management & Rollback

- Each analysis is saved as an independent snapshot with full metadata
- Compare knowledge point counts and analysis results across versions
- One-click version switching and rollback with confirmation workflow
- Agent status tracking per version showing individual category analysis results

### 8. i18n Internationalization

- Full support for **English** and **Simplified Chinese (中文)**
- Language switcher with persistent preference storage
- All UI components, analysis status labels, and data displays are translated
- Easily extensible for additional languages

---

## 📦 Technology Stack

### Frontend (Next.js 15)

| Category | Technology |
|----------|-----------|
| **Framework** | Next.js 15 App Router |
| **Styling** | Tailwind CSS 4 |
| **State Management** | Zustand |
| **Data Fetching** | React Query (TanStack Query) |
| **Graph Visualization** | XFlow (AntV) |
| **Code Highlighting** | Shiki |
| **Icons** | lucide-react |
| **Internationalization** | react-i18next |
| **Animations** | Framer Motion |

### Backend (Python 3.12+)

| Category | Technology |
|----------|-----------|
| **Web Framework** | FastAPI |
| **Async Tasks** | Celery + Redis |
| **ORM** | SQLAlchemy 2.0 (Async) |
| **Agent Orchestration** | LangGraph |
| **Code Parsing** | Tree-sitter |
| **Full-Text Search** | Meilisearch |
| **Vector Search** | pgvector |
| **Authentication** | API Key |

### AI & LLM

| Component | Purpose |
|-----------|---------|
| LangChain / LangGraph | Agent workflow orchestration and state management |
| LiteLLM | Unified multi-model interface (OpenAI, Anthropic, Ollama) |
| Sentence Transformers | Text embedding and vectorization |
| pgvector | Vector storage and similarity search |

### Infrastructure

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Relational data storage + pgvector extension |
| Redis | 6379 | Celery task queue + caching |
| Meilisearch | 7700 | Full-text search engine |
| Celery Worker | - | Async task processing |
| FastAPI | 8000 | REST API service |
| Next.js | 3000 | Frontend application |

---

## 🏗️ Project Structure

```
CodeInsightAi/
├── codeinsight-backend/                # Python FastAPI backend
│   ├── codeinsight/                    # Main application package
│   │   ├── main.py                     # FastAPI application entry point
│   │   ├── config.py                   # Configuration (Pydantic Settings)
│   │   ├── exceptions.py               # Custom exceptions
│   │   ├── dependencies.py             # DI dependency injection
│   │   ├── api/                        # API route modules (14 endpoints)
│   │   │   ├── repositories.py         # Repository management
│   │   │   ├── analysis.py             # Analysis tasks
│   │   │   ├── knowledge.py            # Knowledge points
│   │   │   ├── search.py               # Search
│   │   │   ├── ast_nodes.py            # AST nodes
│   │   │   ├── call_edges.py           # Call graph edges
│   │   │   ├── versions.py             # Version management
│   │   │   └── ...
│   │   ├── models/                     # SQLAlchemy models
│   │   ├── schemas/                    # Pydantic schemas
│   │   ├── services/                   # Business logic services
│   │   │   ├── llm/                    # LLM client
│   │   │   ├── scanners/              # Code scanners
│   │   │   ├── parsers/               # Parsers
│   │   │   ├── engines/               # Core engines
│   │   │   │   ├── call_graph.py      # Call graph generation
│   │   │   │   ├── module_graph.py    # Module dependency graph
│   │   │   │   └── framework_detector.py
│   │   │   └── services.py
│   │   ├── agents/                     # AI Agents (LangGraph)
│   │   │   ├── planning_agent.py
│   │   │   ├── parsing_agent.py
│   │   │   ├── reasoning_agent.py
│   │   │   └── synthesis_agent.py
│   │   ├── tasks/                      # Celery tasks
│   │   ├── pipelines/                  # Analysis pipelines
│   │   ├── evaluation/                 # Evaluation framework
│   │   ├── db/                         # Database session management
│   │   ├── embedding/                  # Vector embedding
│   │   └── utils/                      # Utility functions
│   ├── alembic/                        # Database migrations
│   ├── tests/                          # pytest test suite (30+ test files)
│   ├── scripts/                        # Utility scripts
│   │   ├── export_openapi.py           # OpenAPI spec export for frontend types
│   │   └── seed_test_data.py           # Test data seeding
│   ├── pyproject.toml                  # Dependency management (Uv)
│   └── README.md
│
├── codeinsight-frontend/               # Next.js frontend application
│   ├── src/
│   │   ├── app/                        # App Router pages
│   │   │   ├── page.tsx                # Home page (dashboard)
│   │   │   ├── layout.tsx              # Global layout
│   │   │   ├── repositories/           # Repository management pages
│   │   │   ├── knowledge/              # Knowledge base pages
│   │   │   └── search/                 # Search page
│   │   ├── components/                 # UI components
│   │   │   ├── analysis/              # Analysis visualization components
│   │   │   ├── call-graph/            # Call graph components
│   │   │   ├── structure/             # AST structure components
│   │   │   └── ...
│   │   ├── i18n/                       # Internationalization (en-US, zh-CN)
│   │   ├── hooks/                      # React hooks
│   │   ├── api/                        # API client
│   │   └── utils/                      # Utility functions
│   ├── next.config.ts
│   ├── tsconfig.json
│   └── package.json
│
├── packages/shared/                    # Shared TypeScript types
│   ├── src/
│   │   ├── constants.ts               # UI constants and config mappings
│   │   └── generated.ts               # Auto-generated from OpenAPI
│   ├── tsconfig.json
│   └── package.json
│
├── doc/                                # Documentation
│   ├── code-analysis-dev-roadmap/      # Development roadmap
│   └── dev-analysis/                   # Feature analysis reports
│
├── dev-report/                         # Development progress reports
├── docker-compose.yml                  # Service orchestration
├── package.json                        # Root workspace management
└── README.md
```

---

## 🧪 Testing & Quality Assurance

### Test Commands

```bash
# Run all tests
npm run test

# Backend tests only
cd codeinsight-backend && pytest

# Frontend tests only
cd codeinsight-frontend && npm test

# With coverage report
pytest --cov=codeinsight --cov-report=html

# Run linter
npm run lint

# Format code
npm run format
```

### Code Quality

| Tool | Configuration |
|------|---------------|
| Ruff | Code linting (fast), line width 120, target Python 3.12 |
| Mypy | Static type checking with strict mode |
| ESLint | TypeScript linting with Next.js plugin |
| Prettier | Code formatting |

---

## 🤝 Contributing

Contributions are welcome! Please read [DEVELOPMENT-STANDARDS.md](doc/code-analysis-dev-roadmap/DEVELOPMENT-STANDARDS.md) for code style guidelines and development workflow.

### Development Workflow

```bash
# 1. Create a feature branch
git checkout -b feat/new-feature

# 2. Develop and commit
git add .
git commit -m "feat: implement new feature"

# 3. Push and create a PR
git push origin feat/new-feature

# 4. Run CI tests
# Ensure all checks pass before merging
```

---

## 📄 License

MIT © [Your Organization](https://github.com/your-org)

## 🙌 Acknowledgements

- [LangChain](https://langchain.ai/) and [LangGraph](https://langchain-langgraph.github.io/langgraph/) for powerful Agent orchestration frameworks
- [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) for cross-language syntax parsing
- [Meilisearch](https://meilisearch.com/) for fast full-text search
- [FastAPI](https://fastapi.tiangolo.com/) for the modern Python web framework
- [XFlow](https://xflow.antv.vision/) for graph visualization
- [Next.js](https://nextjs.org/) for the React framework