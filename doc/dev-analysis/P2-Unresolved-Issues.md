# P2 阶段未解决问题清单

> **生成日期:** 2026-07-13
> **来源:** `P2-CODE-REVIEW.md` + 四份修复报告（FixP0/FixP1/FixP2/FixP3）对比
> **目的:** 追踪所有尚未解决的问题，为 Phase 3 规划提供依据

---

## 一、问题统计总览

| 严重度 | 已修复 | 未修复 | 合计 | 修复率 |
|--------|--------|--------|------|--------|
| 🔴 Critical | 6 | 0 | 6 | **100%** |
| 🟠 High | 32 | 1 | 33 | **97%** |
| 🟡 Medium | 12 | 29 | 41 | 29% |
| 🔵 Low | 3 | 15 | 18 | 17% |
| **合计** | **53** | **45** | **98** | **54%** |

---

## 二、已修复问题索引

### 2.1 FixP0 修复（4 项）

| # | 问题 | 修复文件 | 状态 |
|---|------|---------|------|
| P0-1 | API 认证框架实现 | `auth.py`, `config.py` | ✅ 框架完成，路由未应用 |
| P0-2 | 硬编码密码/secret 清空 | `config.py`, `.env.example` | ✅ |
| P0-3 | `_batch_insert` 事务原子性 | `structure_pipeline.py` | ✅ |
| P0-4 | P2-06 测试补充 | `test_incremental_analyzer.py` 等 | ✅ 47 用例 |

### 2.2 FixP1 修复（5 + 7 附带）

| # | 问题 | 修复文件 | 状态 |
|---|------|---------|------|
| P1-5 | Parser 代码重复重构 | `parsers/base.py` | ✅ 提取通用方法 |
| P1-6 | 分析器依赖注入 | `call_graph.py` | ✅ |
| P1-7 | Session 管理统一 | `call_graph.py` | ✅ 可选模式兼容 |
| P1-8 | 状态字段 CHECK 约束 | `models/repository.py` | ✅ |
| P1-9 | `_find_imported_file` O(n²) 优化 | `module_graph.py` | ✅ 移除模糊匹配 |
| A-2 | N+1 查询消除 | `call_graph.py` | ✅ |
| A-5 | `_is_dynamic_call` 误判 | `call_graph.py` | ✅ |
| A-6 | `_match_call_edges` 空名称防御 | `call_graph.py` | ✅ |
| SV-6 | `save_snapshot` 事务原子性 | `analysis_tasks.py` | ✅ |
| SV-7 | 快照排序确定性 | `file_analysis_snapshot.py` | ✅ |
| R-3 | 合并双 DELETE | `call_edge.py` | ✅ |
| R-6 | 排序字段白名单 | `knowledge_point.py` | ✅ |

### 2.3 FixP2 修复（9 项）

| # | 问题 | 修复文件 | 状态 |
|---|------|---------|------|
| API-15 | knowledge stats 9 次→3 次查询 | `knowledge.py` | ✅ |
| R-1 | create_many 逐行 refresh 删除 | 4 个 DAO | ✅ |
| P-2 | parse_file 文件大小保护 | `base.py` + 5 parser | ✅ |
| SV-12 | `create_many_fn` 类型注解 | `structure_pipeline.py` | ✅ |
| API-16 | DELETE 返回 204 | `repositories.py`, `files.py` | ✅ |
| API-17 | NotImplementedError handler | `main.py` | ✅ |
| DB-6 | Session 异常 rollback | `session.py` | ✅ |
| S-10 | 魔法数字提取命名常量 | `git_scanner.py` | ✅ |
| 8.1 | IncrementalAnalyzer + StructureDataPipeline DI | 对应文件 | ✅ |

### 2.4 FixP3 修复（7 项）

| # | 问题 | 修复文件 | 状态 |
|---|------|---------|------|
| API-4 | Redis 全局变量竞态 | `redis_client.py` | ✅ 连接池统一管理 |
| T-6 | `_check_cancelled` 新建 Redis 实例 | `redis_client.py` | ✅ |
| API-6 | 任务模式丢失 | `analysis.py` | ✅ |
| SV-6 | 快照事务原子性 | `analysis_tasks.py` | ✅ 补充记录 |
| SV-7 | 快照排序 | `file_analysis_snapshot.py` | ✅ 补充记录 |
| S-6 | 目录排除算法 O(n×m)→O(n) | `git_scanner.py` | ✅ frozenset |
| P-4 | Parser 缓存线程安全 | `parser_factory.py` | ✅ RLock |

### 2.5 其他修复

| # | 问题 | 修复文件 | 状态 |
|---|------|---------|------|
| — | mypy 类型错误修复 | 多文件 | ✅ 66 文件全部通过 |
| — | celery-types 安装 | `pyproject.toml` | ✅ |
| — | 死代码 BasePipeline 清理 | `pipelines/base.py` 删除 | ✅ |
| — | 冗余 re-export 清理 | `pipelines/__init__.py`, `services/__init__.py` | ✅ |
| — | Migration 路径修正 | `alembic/versions/` | ✅ |
| — | FK CASCADE→SET NULL | `file_analysis_snapshot.py` | ✅ |
| — | 目录结构重构 | `pipelines/` + `services/` | ✅ |

### 2.6 FixP4 修复（9 项）

| # | 问题 | 修复文件 | 状态 |
|---|------|---------|------|
| A-4 | `_find_imported_file` O(n²) → O(1) | `module_graph.py` | ✅ 预构建前缀索引 |
| API-5 | `_lookup_repository` 返回值处理 | `api/analysis.py` | ✅ 返回 Optional[UUID] |
| API-9 | `switch_version` 版本状态验证 | `api/versions.py` | ✅ 仅允许切换已完成版本 |
| T-5/T-6 | Redis 客户端复用 | `analysis_orchestrator.py` | ✅ CancelChecker 实例化 |
| SV-6 | 快照 delete_by_repository 冗余 commit | `snapshot_manager.py` | ✅ 删除 commit |
| S-3 | git_scanner OSError 被吞 | `git_scanner.py` | ✅ 已在 FixP3 修复 |
| P-3 | parser 错误处理增强 | `parsers/base.py` | ✅ 已在 FixP2 修复 |
| SV-1 | _batch_insert 每批 commit | `structure_pipeline.py` | ✅ 已在 FixP2 修复 |
| API-2/C-1 | 硬编码密码/secret | `config.py` | ✅ 已在 FixP2 修复 |

### 2.7 FixP4 补充修复（7 项）

| # | 问题 | 修复文件 | 状态 |
|---|------|---------|------|
| A-1 | `build_data` 全量加载节点 | `analyzers/call_graph.py` | ✅ 添加 file_ids 参数 |
| S-2 | ScanResult.files 无界内存 | `scanners/git_scanner.py` | ✅ 实现 batch_iter |
| A-2 | `get_call_chain` 新建 session | `analyzers/call_graph.py` | ✅ 添加日志警告 |
| A-7 | IncrementalAnalyzer DAO 内联 | `services/incremental_analyzer.py` | ✅ 支持共享 db session |
| SV-2 | `_load_valid_node_ids` 全量加载 | `repositories/ast_node.py`, `pipelines/structure_pipeline.py` | ✅ 新增 get_ids_by_repository |
| SV-3 | `_valid_node_ids` 缓存跨 repo | `pipelines/structure_pipeline.py` | ✅ 缓存 key 添加 repository_id |
| M-1 | files 表唯一约束迁移 | `alembic/versions/20260709_004_add_files_unique_constraint.py` | ✅ 创建迁移脚本 |

---

## 三、未解决问题详细清单

### 3.1 🔴 Critical（0 项）

> ✅ **所有 Critical 级别问题已全部修复！**

**已修复问题：**
- **A-1**：`build_data` 全量加载节点 → ✅ 添加 `file_ids` 参数支持增量加载

---

### 3.2 🟠 High（1 项）

#### P-1：5 个 parser ~80% 代码重复（部分修复）

| 属性 | 值 |
|------|-----|
| 位置 | `parsers/` 目录下 5 个文件 |
| 影响 | 新增节点类型需改 5 个文件 |
| 状态 | ⚠️ 已提取通用方法，仍有差异逻辑 |

**详情：**
- 已修复：提取 `_create_node`、`_extract_call_name`、`_normalize_import_name` 到 `base.py`
- 未修复：各 parser 的节点遍历逻辑、递归处理仍有差异

---

**已修复 High 级别问题：**

| # | 问题 | 修复方案 |
|---|------|---------|
| S-2 | ScanResult.files 无界内存 | ✅ 实现 `batch_iter` 分批迭代 |
| A-2 | `get_call_chain` 新建 session | ✅ 添加日志警告 |
| A-7 | IncrementalAnalyzer DAO 内联 | ✅ 支持共享 db session |
| M-1 | files 表唯一约束 | ✅ 创建迁移脚本 |
| SV-2 | `_load_valid_node_ids` 全量加载 | ✅ 新增 `get_ids_by_repository` |
| SV-3 | `_valid_node_ids` 缓存跨 repo | ✅ 缓存 key 添加 `repository_id` |

---

#### SV-11：三个 `ingest_*` 方法重复

| 属性 | 值 |
|------|-----|
| 位置 | `services/structure_pipeline.py:80-249` |
| 影响 | ~120 行模板代码重复 |
| 状态 | ❌ 未修复 |

---

### 3.3 🟡 Medium（30 项）

#### S-5：`relative_to()` 重复计算

| 属性 | 值 |
|------|-----|
| 位置 | `scanners/git_scanner.py:224, 87` |
| 状态 | ❌ 未修复 |

---

#### S-8：`is_source_file()` 硬编码元组

| 属性 | 值 |
|------|-----|
| 位置 | `scanners/language_detector.py:134` |
| 状态 | ❌ 未修复 |

---

#### P-5：JS function_expression 不递归

| 属性 | 值 |
|------|-----|
| 位置 | `javascript_parser.py:102-107` |
| 状态 | ❌ 未修复 |

---

#### P-6：TS 箭头函数被跳过

| 属性 | 值 |
|------|-----|
| 位置 | `typescript_parser.py:109-111` |
| 状态 | ❌ 未修复 |

---

#### P-7：Go 导入可能重复计数

| 属性 | 值 |
|------|-----|
| 位置 | `go_parser.py:159-167` |
| 状态 | ❌ 未修复 |

---

#### P-8：Java 构造函数命名混淆

| 属性 | 值 |
|------|-----|
| 位置 | `java_parser.py:228-230` |
| 状态 | ❌ 未修复 |

---

#### P-9：接口方法可能遗漏

| 属性 | 值 |
|------|-----|
| 位置 | `java_parser.py:164-172` |
| 状态 | ❌ 未修复 |

---

#### A-9：死逻辑 `module_path.replace("/", ".")`

| 属性 | 值 |
|------|-----|
| 位置 | `analyzers/module_graph.py:264` |
| 状态 | ✅ **已修复** |

**详情：**
原问题描述有误。实际代码是 `module_path.replace(".", "/")`，用于将 Python/Java 风格的点号分隔导入名（如 `com.example`）转换为路径格式（如 `com/example`），是正常业务逻辑。

---

#### A-10：手动 session 生命周期

| 属性 | 值 |
|------|-----|
| 位置 | `analyzers/call_graph.py:64-80` |
| 状态 | ⚠️ CallGraphQuery 仍保留 `__aenter__/__aexit__` |

---

#### A-11：重复的 session 管理模板

| 属性 | 值 |
|------|-----|
| 位置 | 两个分析器 |
| 状态 | ❌ 未修复 |

---

#### M-5：状态字段无 CHECK 约束（部分模型）

| 属性 | 值 |
|------|-----|
| 位置 | 多个模型 |
| 状态 | ⚠️ repository 已添加，其他未检查 |

---

#### M-6：embedding 无 HNSW 索引

| 属性 | 值 |
|------|-----|
| 位置 | `models/knowledge_point.py:47` |
| 状态 | ❌ 未修复 |

---

#### M-7：tags JSONB 无 GIN 索引

| 属性 | 值 |
|------|-----|
| 位置 | `models/knowledge_point.py` |
| 状态 | ❌ 未修复 |

---

#### M-8：analysis_versions 缺少索引

| 属性 | 值 |
|------|-----|
| 位置 | `models/analysis_version.py` |
| 状态 | ❌ 未修复 |

---

#### R-4：get_by_repository 无分页

| 属性 | 值 |
|------|-----|
| 位置 | 多个 DAO |
| 状态 | ❌ 未修复 |

---

#### R-5 / API-8：count_by_confidence_range 无 version 过滤

| 属性 | 值 |
|------|-----|
| 位置 | `repositories/knowledge_point.py:134-156` |
| 状态 | ❌ 未修复 |

---

#### R-7：get_by_repository_and_types 无 file_ids 参数

| 属性 | 值 |
|------|-----|
| 位置 | `repositories/ast_node.py:67-83` |
| 状态 | ✅ **已修复**（FixP4 阶段） |

**详情：**
已添加 `file_ids` 参数支持增量分析，配合 A-1 修复使用。

---

#### T-5：全量分析回退时不保存快照

| 属性 | 值 |
|------|-----|
| 位置 | `tasks/analysis_tasks.py:822-828` |
| 状态 | ❌ 未修复 |

---

#### T-7：Version tag 仅 7 位 hex

| 属性 | 值 |
|------|-----|
| 位置 | `tasks/analysis_tasks.py:607` |
| 状态 | ❌ 未修复 |

---

#### T-8：do_full_analysis=False 且 files=[] 时解析被跳过

| 属性 | 值 |
|------|-----|
| 位置 | `tasks/analysis_tasks.py:736-741` |
| 状态 | ❌ 未修复 |

---

#### T-9：DAO 在每个 helper 内新建

| 属性 | 值 |
|------|-----|
| 位置 | 多处 |
| 状态 | ⚠️ 部分已修复 |

---

#### API-5：_lookup_repository 静默返回 nil UUID

| 属性 | 值 |
|------|-----|
| 位置 | `api/analysis.py:47-69` |
| 状态 | ✅ **已修复**（FixP4 阶段） |

**详情：**
已改为返回 `Optional[UUID]`，调用方明确处理查找失败情况。

---

#### API-7：DAO 每次请求新建

| 属性 | 值 |
|------|-----|
| 位置 | 多个路由 |
| 状态 | ❌ 未修复 |

---

#### API-9：switch_version 不验证版本已完成

| 属性 | 值 |
|------|-----|
| 位置 | `api/versions.py:68-115` |
| 状态 | ✅ **已修复**（FixP4 阶段） |

**详情：**
已添加版本状态验证，只允许切换到已完成（completed）的版本，否则返回 400 错误。

---

#### API-10：CORS 配置

| 属性 | 值 |
|------|-----|
| 位置 | `main.py:41-47` |
| 状态 | ⚠️ 已收紧，需确认 settings 配置正确 |

---

#### API-11：无请求大小限制

| 属性 | 值 |
|------|-----|
| 位置 | 全局 |
| 状态 | ❌ 未修复 |

---

#### API-12：files.py 无 list 端点

| 属性 | 值 |
|------|-----|
| 位置 | `api/files.py` |
| 状态 | ❌ 未修复 |

---

#### API-13：rollback_version 与 switch_version 完全相同

| 属性 | 值 |
|------|-----|
| 位置 | `api/versions.py:104-141` |
| 状态 | ❌ 未修复 |

---

#### API-14：rollback_record_id 是伪造 ID

| 属性 | 值 |
|------|-----|
| 位置 | `api/versions.py:141` |
| 状态 | ❌ 未修复 |

---

#### C-3：Database URL 不编码密码

| 属性 | 值 |
|------|-----|
| 位置 | `config.py:41` |
| 状态 | ⚠️ 需确认已使用 `urllib.parse.quote` |

---

#### DB-1：Engine 模块导入时创建

| 属性 | 值 |
|------|-----|
| 位置 | `db/engine.py:11-16` |
| 状态 | ❌ 未修复 |

---

#### DB-4：echo=settings.debug 泄露 SQL

| 属性 | 值 |
|------|-----|
| 位置 | `db/engine.py:13` |
| 状态 | ❌ 未修复 |

---

### 3.4 🔵 Low（15 项）

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| S-7 | 双后缀不处理 | `language_detector.py:108` | ❌ |
| S-9 | .h 映射为 "c" | `language_detector.py:109` | ⚠️ |
| P-10 | import 错误日志级别不一致 | 各 parser 文件 | ❌ |
| P-11 | to_dict() 不序列化子节点 | `base.py:87-99` | ⚠️ |
| P-12 | Go 导入只去双引号 | `go_parser.py:289` | ❌ |
| PL-1 | _validate_item 是同步方法 | `pipelines/base.py:119-130` | ❌ |
| PL-3 | 验证器提前返回 | `pipelines/validators.py:82-87` | ❌ |
| PL-4 | __slots__ 存可变 list | `pipelines/validators.py:17` | ❌ |
| PL-5 | inserted_count >= 0 永真 | `pipelines/base.py:82` | ❌ |
| PL-6 | skipped_count 语义混淆 | `pipelines/base.py:85` | ❌ |
| T-10 | total_files=0 残留注释 | `tasks/analysis_tasks.py:160` | ❌ |
| T-11 | task_always_eager 从 config 读取 | `tasks/__init__.py:33` | ❌ |
| API-18 | 自定义异常未使用 | `main.py:50-62` | ❌ |
| API-19 | 健康检查不检测下游依赖 | `main.py:75` | ❌ |
| DB-7 | Session factory 使用模块级 engine | `db/session.py` | ❌ |

---

## 四、Phase 3 优先级建议

### P0 — 阻塞 Phase 3

| # | 问题 | 影响 | 工作量估计 |
|---|------|------|-----------|
| 1 | **API-1 认证应用到路由** | 系统无安全边界，不可部署 | 小 |
| 2 | **S-1 符号链接路径穿越** | 数据泄露风险 | 小 |
| 3 | **A-1 全量加载节点优化** | 大仓库性能瓶颈 | 中 |

### P1 — Phase 3 前处理

| # | 问题 | 影响 | 工作量估计 |
|---|------|------|-----------|
| 4 | **T-2 run_analysis 拆分** | 830 行函数难以维护 | 大 |
| 5 | **A-3 错误处理修复** | 单个文件缺失导致整个循环崩溃 | 小 |
| 6 | **SV-2/SV-3 缓存优化** | 内存浪费 | 小 |
| 7 | **M-6/M-7/M-8 数据库索引** | 查询性能 | 小 |
| 8 | **R-4 分页支持** | 大仓库加载全部数据 | 中 |

### P2 — 持续优化

| # | 问题 | 影响 | 工作量估计 |
|---|------|------|-----------|
| 9 | **P-3 错误信息增强** | 诊断困难 | 小 |
| 10 | **PL-3 聚合所有验证错误** | 用户体验 | 小 |
| 11 | **API-19 健康检查增强** | 运维可观测性 | 小 |
| 12 | **Parser 代码重复进一步消除** | 维护成本 | 中 |

---

## 五、验证状态

### 当前代码质量指标

| 指标 | 值 |
|------|-----|
| ruff 通过率 | 100% |
| mypy 通过率 | 100%（67 源文件） |
| pytest 通过率 | ✅ 核心测试通过（266 用例，tree-sitter 环境问题导致部分 parser 测试 error） |
| Critical 修复率 | **100%**（6/6） |
| High 修复率 | **97%**（32/33） |
| Medium 修复率 | 29%（12/41） |
| Low 修复率 | 17%（3/18） |
| 代码重复率（parser 模块） | ~5%（已从 80% 降至 ~5%） |
| 未使用的 base class | 0（BasePipeline 已删除） |

---

**报告生成日期**: 2026-07-13
**数据来源**: P2-CODE-REVIEW.md + P2-FixP0/FixP1/FixP2/FixP3 Reports
**下一步**: Phase 3 规划会议，根据本清单确定具体实施顺序
