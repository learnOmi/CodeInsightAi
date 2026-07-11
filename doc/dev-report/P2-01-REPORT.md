# P2-01: 代码扫描器 — GitPython 仓库打开 + pathlib 递归文件收集

## 一、任务概述

| 项目 | 内容 |
|------|------|
| 任务编号 | P2-01 |
| 任务名称 | 代码扫描器：GitPython 仓库打开 + pathlib 递归文件收集 |
| 所属阶段 | Phase 2（第 4-6 周） |
| 优先级 | P0 |
| 预估工时 | 10h |
| 交付物 | 文件收集器（支持 .gitignore 过滤）+ 单元测试 |

### 前置依赖

| 依赖 | 状态 | 说明 |
|------|------|------|
| P1-08 Celery 任务框架 | ✅ | `run_analysis` 任务骨架已就绪 |
| P1-05 RepositoryModel | ✅ | 仓库路径字段已存在 |
| P1-07 RepositoryDAO | ✅ | DAO 层已就绪 |
| GitPython 依赖 | ✅ | `pyproject.toml` 已声明 |

---

## 二、整体架构位置

P2-01 在 CodeInsight 分析管线中的位置：

```
┌──────────────────────────────────────────────────────────────────────┐
│  用户提交分析请求                                                      │
│  POST /api/v1/repositories/:id/analyze                               │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Celery Worker (analysis_tasks.py)                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ run_analysis(self, repository_id, mode, agents)              │   │
│  │                                                              │   │
│  │  Step 1: 创建版本记录 (_do_analysis_setup)                   │   │
│  │         → 写入 analysis_versions 表                           │   │
│  │         → 更新 repository.status = "analyzing"                │   │
│  │                                                              │   │
│  │  Step 2: 扫描文件 ←── P2-01 实现                             │   │
│  │         ┌────────────────────────────────────────────┐      │   │
│  │         │ GitScanner(repo.path).scan()               │      │   │
│  │         │  → LanguageDetector.detect()               │      │   │
│  │         │  → 分块读取 + SHA-256 hash                 │      │   │
│  │         │  → 返回 ScanResult                         │      │   │
│  │         └────────────────────────────────────────────┘      │   │
│  │                                                              │   │
│  │  Step 3: AST 解析 ←── P2-02 (待实现)                        │   │
│  │         Tree-sitter 解析每个文件 → 语法树                    │   │
│  │                                                              │   │
│  │  Step 4: AI 分析 ←── P2-05 (待实现)                          │   │
│  │         LangGraph Agent → 设计模式/反模式检测                 │   │
│  │                                                              │   │
│  │  Step 5: 存储结果 ←── P2-03/P2-04 (API 层)                  │   │
│  │         写入 knowledge_points 表                              │   │
│  │                                                              │   │
│  │  Step 6: 完成                                                │   │
│  │         更新 repository.status = "completed"                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 数据流向

```
Git 仓库文件系统
    │
    │  GitScanner.scan()
    ▼
┌─────────────────────────────────────────┐
│  ScanResult                             │
│  ├── total_count: 1250                  │
│  ├── total_lines: 34,210               │
│  ├── language_distribution:             │
│  │   {"python": 800, "typescript": 450} │
│  ├── skipped_count: 320                 │
│  └── files: [ScannedFile, ...]          │
│      └── ScannedFile:                   │
│          ├── path: "src/main.py"        │
│          ├── language: "python"         │
│          ├── line_count: 156            │
│          ├── size_bytes: 4,210          │
│          └── content_hash: "sha256..."  │
└─────────────────────────────────────────┘
    │
    │  P2-02: Tree-sitter 解析
    │  (按 language 选择解析器)
    ▼
AST 语法树 → P2-05: LLM Agent 分析 → knowledge_points 表
```

---

## 三、实现模块结构

```
codeinsight/scanners/
├── __init__.py              # 模块导出
├── language_detector.py     # 语言检测器（扩展名映射）
└── git_scanner.py           # Git 仓库扫描器

tests/
├── test_language_detector.py # 语言检测器单元测试（14 个用例）
└── test_git_scanner.py       # Git 扫描器单元测试（9 个用例）
```

---

## 四、核心类设计

### 4.1 LanguageDetector — 语言检测器

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `detect(file_path)` | `str` | 通过扩展名检测语言 |
| `is_supported(file_path)` | `bool` | 是否在 Tree-sitter 支持列表中 |
| `is_source_file(file_path)` | `bool` | 是否为源代码文件（排除文档/配置） |

**支持的语言**：python, javascript, typescript, java, go, rust, c, cpp, csharp, ruby, php, swift, kotlin

**文件元数据结构**（`ScannedFile`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `str` | 仓库内相对路径 |
| `absolute_path` | `str` | 绝对路径 |
| `language` | `str` | 语言类型 |
| `line_count` | `int` | 代码行数 |
| `size_bytes` | `int` | 文件大小 |
| `content_hash` | `str` | SHA-256 内容 hash |

### 4.2 GitScanner — Git 仓库扫描器

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `scan(language_detector)` | `ScanResult` | 执行扫描，返回结果 |
| `_open_repo()` | `git.Repo \| None` | 打开 Git 仓库，失败降级为 pathlib |

**扫描过滤规则**（多层漏斗）：

```
全部文件
  │
  ├── 1. 默认排除目录 (.git, node_modules, __pycache__...)
  │
  ├── 2. .gitignore 过滤 (GitPython .ignored())
  │
  ├── 3. 语言检测 (只保留源代码文件)
  │
  ├── 4. 文件大小检查 (>10MB → 跳过)
  │
  └── 5. 行数检查 (>10000 行 → 跳过)
```

---

## 五、内存安全优化

### 5.1 问题：`read_bytes()` 的 OOM 风险

**原始实现**：

```python
content = file_path.read_bytes()  # 一次性加载整个文件
content_hash = hashlib.sha256(content).hexdigest()
```

**风险**：即使后续检查 `size_bytes > 10MB` 并跳过，`read_bytes()` 已经将整个文件加载到内存中。对于大文件（如 minified JS bundle 100MB+），会导致 OOM。

### 5.2 修复：流式分块读取

**修复后实现**：

```python
# 1. 先 stat() 检查大小，零内存开销
size_bytes = file_path.stat().st_size
if size_bytes > 10 * 1024 * 1024:
    return None

# 2. 分块读取，最大内存占用 ~64KB
_buffer_size = 64 * 1024
sha = hashlib.sha256()
line_count = 0
partial_line = 0

with open(file_path, "rb") as f:
    while True:
        chunk = f.read(_buffer_size)
        if not chunk:
            break
        sha.update(chunk)
        line_count += chunk.count(b"\n")
        if not chunk.endswith(b"\n"):
            partial_line = 1

content_hash = sha.hexdigest()
```

### 5.3 优化效果对比

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| **最大内存占用** | 文件大小（无上限） | 64KB（固定） |
| **大文件处理** | 读入内存后跳过 | 直接跳过（零内存） |
| **二进制文件** | 尝试 decode 报错 | 直接跳过 decode |
| **100MB 文件** | OOM | 瞬间跳过 |
| **行数计算** | 全量 decode | 二进制 `\n` 计数 |

### 5.4 其他内存保护机制

| 机制 | 实现 | 说明 |
|------|------|------|
| 文件大小上限 | `stat().st_size > 10MB` | 跳过超大文件 |
| 行数上限 | `line_count > 10000` | 跳过超大文件 |
| 排除目录 | 16 个默认排除目录 | 跳过构建产物、缓存 |
| 流式读取 | 64KB 分块 | 固定内存上限 |

---

## 六、集成到 `run_analysis`

在 `analysis_tasks.py` 的 Step 2（扫描文件阶段）中：

```python
from codeinsight.scanners.git_scanner import GitScanner

repo_dao = RepositoryDAO()
repo = asyncio.run(repo_dao.get_by_id(async_session_factory(), repo_uuid))
if repo is not None:
    scanner = GitScanner(repo.path)
    scan_result = scanner.scan()
    total_files = scan_result.total_count
    logger.info("扫描完成: repo=%s, files=%d, lines=%d",
                repo.path, total_files, scan_result.total_lines)
    logger.info("语言分布: %s", scan_result.language_distribution)
```

**注意**：扫描在 Celery worker 进程内同步执行，非阻塞。

---

## 七、测试覆盖

### 7.1 test_language_detector.py（14 个用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_detect_python` | Python 扩展名检测 |
| `test_detect_javascript` | JS/JSX 检测 |
| `test_detect_typescript` | TS/TSX 检测 |
| `test_detect_java` | Java 检测 |
| `test_detect_go` | Go 检测 |
| `test_detect_rust` | Rust 检测 |
| `test_detect_c` | C 检测 |
| `test_detect_cpp` | C++ 检测 |
| `test_detect_unknown` | 未知扩展名 |
| `test_is_supported_*` | 支持/不支持判断 |
| `test_is_source_file_*` | 源代码/非源代码判断 |

### 7.2 test_git_scanner.py（9 个用例）

| 测试 | 覆盖内容 |
|------|---------|
| `test_scan_returns_scanned_files` | 扫描返回文件列表 |
| `test_scan_filters_gitignore` | .gitignore 过滤 |
| `test_scan_filters_excluded_dirs` | 默认排除目录过滤 |
| `test_scan_filters_non_source` | 非源代码文件过滤 |
| `test_scan_language_distribution` | 语言分布统计 |
| `test_scan_file_content_hash` | SHA-256 hash 计算 |
| `test_scan_skipped_count` | 跳过文件计数 |
| `test_scan_non_git_repo` | 非 Git 仓库降级扫描 |
| `test_scan_empty_repo` | 空仓库处理 |

### 7.3 现有测试更新

| 文件 | 改动 |
|------|------|
| `test_analysis_tasks.py` | 为 3 个 `run_analysis` 测试添加 `GitScanner` mock，使用正确的 mock 路径 `codeinsight.scanners.git_scanner.GitScanner` |
| `test_git_scanner.py` | 添加 `.gitignore` fixture 以正确测试 gitignore 过滤 |

---

## 八、验证结果

| 检查项 | 结果 |
|--------|------|
| `pytest` | ✅ **119 passed**, 8 warnings |
| `ruff check` | ✅ All checks passed |
| `mypy codeinsight` | ✅ Success: no issues found in 36 source files |

---

## 九、设计决策

| 决策 | 方案 | 说明 |
|------|------|------|
| GitPython `.ignored()` | 使用内置方法 | 比手动解析 `.gitignore` 更可靠 |
| 非 Git 仓库 | 降级为 pathlib 扫描 | 不依赖 `.gitignore`，但仍应用默认排除目录 |
| 文件 hash 算法 | SHA-256 | 安全且碰撞概率低 |
| **内存读取策略** | **流式 64KB 分块** | 固定内存上限，永不 OOM |
| 语言检测 | 扩展名映射表 | 简单可靠，Tree-sitter 在 P2-02 接入 |
| 行数统计 | 二进制 `\n` 计数 | 无需 decode，支持二进制文件 |

---

## 十、待后续工作

| 任务 | 关联阶段 | 说明 |
|------|---------|------|
| 增量扫描 | P2-06 | 基于 `content_hash` 检测文件变更 |
| Tree-sitter 解析 | P2-02 | 使用 `language` 字段选择正确解析器 |
| 大数据仓库优化 | P2-06 | 分批扫描、异步 IO |
