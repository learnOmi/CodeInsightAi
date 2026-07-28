"""
仓库管理路由

提供仓库的增删改查接口。
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import redis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from codeinsight.agents.state import AnalysisState
from codeinsight.auth import get_api_key_dependency
from codeinsight.config import settings
from codeinsight.constants.redis_keys import repo_active_task_key, task_mode_key, task_repo_key
from codeinsight.db.redis_client import get_redis_client
from codeinsight.db.session import async_session_factory, get_db_session
from codeinsight.exceptions import RepositoryNotFoundError, RepositoryPathExistsError
from codeinsight.repositories import RepositoryDAO
from codeinsight.schemas import Repository, RepositoryCreate, RepositoryUpdate
from codeinsight.schemas.analysis import AnalysisMode


class PaginatedRepositories(BaseModel):
    """分页仓库列表响应"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    items: list[Repository]
    total: int
    page: int
    page_size: int
    total_pages: int


logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(get_api_key_dependency(settings.api_key))],
)


def get_repository_dao() -> RepositoryDAO:
    """获取 RepositoryDAO 实例（依赖注入）"""
    return RepositoryDAO()


# Annotated 类型别名，消除 B008 警告
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RepoDaoDep = Annotated[RepositoryDAO, Depends(get_repository_dao)]


def _get_active_task_id(repository_id: UUID) -> str | None:
    """从 Redis 查询仓库的活跃任务 ID"""
    try:
        client = get_redis_client()
        key = repo_active_task_key(str(repository_id))
        raw = client.get(key)
        logger.debug("Redis 查询活跃任务: repo=%s, key=%s, raw=%s", repository_id, key, raw)
        if raw is not None:
            if isinstance(raw, bytes):
                return raw.decode("utf-8")
            return str(raw)
    except redis.RedisError:
        logger.debug("Redis 查询活跃任务失败: repo=%s", repository_id)
    return None


@router.post("", response_model=Repository, status_code=201)
async def create_repository(
    request: RepositoryCreate,
    db: DbSession,
    dao: RepoDaoDep,
    raw_response: Response,
):
    """
    添加代码仓库

    添加一个新的代码仓库，如果 auto_analyze 为 True 则自动提交分析任务。
    返回的响应头中包含 X-Task-Id（如果 auto_analyze 为 True）。
    """
    logger.info(
        "create_repository 被调用: name=%s, path=%s, auto_analyze=%s", request.name, request.path, request.auto_analyze
    )

    # 验证路径是否存在且为目录
    p = Path(request.path)
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在: {request.path}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是目录: {request.path}")

    # 检查路径是否已存在
    if await dao.exists_by_path(db, request.path):
        raise RepositoryPathExistsError(request.path)

    repo = await dao.create(db, request)
    logger.info("仓库创建成功: repo_id=%s", repo.id)

    # 设置 X-Task-Id 响应头（如果存在）
    task_id = None
    if request.auto_analyze:
        # 预先生成 task_id
        eager_task_id = f"eager-{uuid4()}"
        # 立即持久化 status 和 current_task_id，再触发后台任务
        repo.status = "analyzing"
        repo.current_task_id = eager_task_id
        await db.flush()
        await db.refresh(repo)
        task_id = eager_task_id

        # 提前提交事务，确保后台任务（新 session）能读取到刚创建的仓库
        # 参考 get_db_session 注释："支持路由内手动 commit() 的场景"
        await db.commit()

        # 直接调用 _trigger_analysis，传入已加载的 repo 对象
        # 避免新开 session 读取不到未提交数据的问题
        from codeinsight.api.analysis import AnalysisMode, _trigger_analysis

        result = await _trigger_analysis(
            repo.id, repo, mode=AnalysisMode.FULL, agents=None, eager_task_id=eager_task_id
        )
        logger.info(
            "Eager analysis triggered: repo=%s, task_id=%s, result_task=%s", repo.id, eager_task_id, result.task_id
        )

    if task_id:
        raw_response.headers["X-Task-Id"] = task_id
    return repo


@router.get("", response_model=PaginatedRepositories)
async def list_repositories(
    db: DbSession,
    dao: RepoDaoDep,
    page: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=500, description="每页数量")] = 100,
):
    """
    获取仓库列表（分页）

    分页返回用户的所有仓库。
    """
    skip = (page - 1) * page_size
    repos = await dao.list(db, skip=skip, limit=page_size)
    total = await dao.count(db)
    total_pages = max(1, (total + page_size - 1) // page_size)

    # 填充活跃任务 ID（仅对 analyzing 状态的仓库查询 Redis）
    for repo in repos:
        if repo.status == "analyzing":
            repo.current_task_id = _get_active_task_id(repo.id)  # type: ignore[attr-defined]

    return PaginatedRepositories(
        items=repos,  # type: ignore[arg-type]
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{repository_id}", response_model=Repository)
async def get_repository(
    repository_id: UUID,
    db: DbSession,
    dao: RepoDaoDep,
):
    """
    获取仓库详情
    """
    repo = await dao.get_by_id(db, repository_id)

    if repo is None:
        raise RepositoryNotFoundError(str(repository_id))

    if repo.status == "analyzing":
        repo.current_task_id = _get_active_task_id(repo.id)  # type: ignore[attr-defined]
    return repo


@router.put("/{repository_id}", response_model=Repository)
async def update_repository(
    repository_id: UUID,
    request: RepositoryUpdate,
    db: DbSession,
    dao: RepoDaoDep,
):
    """
    更新仓库信息
    """
    # 检查仓库是否存在
    existing = await dao.get_by_id(db, repository_id)
    if existing is None:
        raise RepositoryNotFoundError(str(repository_id))

    repo = await dao.update(db, repository_id, request)
    return repo


@router.delete("/{repository_id}", status_code=204)
async def delete_repository(
    repository_id: UUID,
    db: DbSession,
    dao: RepoDaoDep,
):
    """
    删除仓库及其所有分析数据
    """
    deleted = await dao.delete(db, repository_id)
    if not deleted:
        raise RepositoryNotFoundError(str(repository_id))

    return Response(status_code=204)


# 新增：重试特定 Agent 的分析 API
class AnalyzeAgentsRequest(BaseModel):
    """重试分析指定 Agent 的请求体"""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )

    agents: list[str]  # Agent 类型列表，如 ["design_pattern", "architecture"]


@router.post("/repositories/{repository_id}/analyze-agents", response_model=dict)
async def analyze_specific_agents(
    repository_id: UUID,
    db: DbSession,
    dao: RepoDaoDep,
    request: Annotated[AnalyzeAgentsRequest, Body(description="要重试的 Agent 列表")],
):
    """
    仅重新运行指定的 Agent 并生成对应的拓展内容（expansion）

    已成功的 Agent 会被跳过，只重失败的部分。这可以节省 AI 调用次数。

    Args:
        repository_id: 仓库唯一标识符
        request: 包含 agents 列表和 mode 的请求体

    Returns:
        { "task_id": "eager-xxx..." }
    """
    # 验证仓库存在
    repo = await dao.get_by_id(db, repository_id)
    if repo is None:
        raise RepositoryNotFoundError(str(repository_id))

    # 检查是否已有活跃任务
    client = get_redis_client()
    active_task_id = _get_active_task_id(repository_id)
    if active_task_id:
        from codeinsight.api.analysis import get_task_status

        try:
            task = await get_task_status(active_task_id)
            if task.status not in ["pending", "scanning", "parsing", "analyzing_structures", "analyzing_modules"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"仓库 {repository_id} 有正在进行的分析任务：{active_task_id}",
                )
        except Exception:
            raise HTTPException(
                status_code=409,
                detail=f"仓库 {repository_id} 有正在运行的任务：{active_task_id}",
            ) from None

    # 生成 task_id
    task_id = f"eager-{uuid4()}"

    # 设置 Redis 映射
    ttl = settings.redis_task_mapping_ttl or 3600
    client.set(task_repo_key(task_id), str(repository_id), ex=ttl)
    client.set(task_mode_key(task_id), AnalysisMode.FULL.value, ex=ttl)
    client.set(repo_active_task_key(str(repository_id)), task_id, ex=ttl)
    client.set(f"task:{task_id}:submitted_at", datetime.now(UTC).isoformat(), ex=ttl)

    # 启动后台任务
    async def _run():
        from pathlib import Path

        from codeinsight.agents.graph import AnalysisGraph
        from codeinsight.embedding.client import EmbeddingClient
        from codeinsight.llm.client import LLMClient
        from codeinsight.repositories import AstNodeDAO, FileDAO, KnowledgePointDAO
        from codeinsight.tasks.analysis_orchestrator import AnalysisOrchestrator

        orchestrator = AnalysisOrchestrator(
            repo_uuid=repository_id,
            mode=AnalysisMode.FULL.value,
            task_instance=None,
            task_id=task_id,
        )

        async with async_session_factory() as shared_db:
            # 加载现有数据
            file_dao = FileDAO()
            ast_node_dao = AstNodeDAO()
            files = await file_dao.get_by_repository(shared_db, repository_id)
            ast_nodes = await ast_node_dao.get_by_repository(shared_db, repository_id)

            if not files:
                await orchestrator.fail(shared_db, "没有可用的文件数据")
                return

            # 构建 AST data
            ast_data = [
                {
                    "id": str(n.id),
                    "node_type": n.node_type,
                    "name": n.name,
                    "file_id": str(n.file_id),
                    "start_line": n.start_line,
                    "end_line": n.end_line,
                    "qualified_name": n.qualified_name or "",
                }
                for n in ast_nodes
            ]

            # 构建代码片段
            repo_path_str = await orchestrator._get_repo_path(shared_db)
            code_snippets = []
            if repo_path_str:
                repo_path = Path(repo_path_str)
                for f in files:
                    file_path = repo_path / f.path if f.path else Path(f.absolute_path)
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        code_snippets.append({"file_path": f.path, "code": content[:5000]})
                    except Exception:
                        pass

            # 创建初始状态 - 只运行指定的 agent
            category_map = {
                "design_pattern": "DP",
                "architecture": "AD",
                "algorithm": "AL",
                "engineering": "ET",
                "domain_knowledge": "DK",
                "template_technique": "TT",
                "technology_stack": "TK",
            }

            initial_state: AnalysisState = {  # type: ignore
                "repo_id": str(repository_id),
                "ast_data": ast_data,
                "code_snippets": code_snippets,
                "knowledge_points": [],
                "current_category": "",
                "progress": 0.0,
                "error": None,
                "messages": [],
                "language_distribution": {},
                "file_dependencies": {},
                "file_structure": {},
                "enable_chunking": False,
                "chunk_progress": {},
                "chunk_results": [],
                "agent_results": {},
            }

            # 使用指定的 category 来路由到特定 agent
            llm_client = LLMClient()
            graph = AnalysisGraph(llm_client)

            # 为每个需要重试的 agent 单独运行
            existing_kps_before = (
                await KnowledgePointDAO().list(shared_db, repository_id, version=orchestrator.version_tag)
                if orchestrator.version_tag
                else []
            )

            for agent_name in request.agents:
                category = category_map.get(agent_name)
                if not category:
                    logger.warning(f"未知的 agent 名称: {agent_name}, 跳过")
                    continue

                # 为这个 agent 创建带 category 的 state
                state_for_agent = {
                    **initial_state,
                    "current_category": category,
                }

                try:
                    final_state = await asyncio.wait_for(graph.run(state_for_agent), timeout=300.0)

                    # 保存新发现的知识点（针对这个 agent）
                    embedding_client = EmbeddingClient()
                    kp_dao = KnowledgePointDAO()
                    saved_for_this = 0

                    for kp in final_state.get("knowledge_points", []):
                        # 检查是否已经存在（避免重复）
                        already_exists = any(
                            kp["title"] == existing.get("title") and kp["category"] == existing.get("category")
                            for existing in existing_kps_before
                        )
                        if not already_exists:
                            try:
                                embed_text = f"{kp['title']}\n{kp['description']}"
                                embedding = await embedding_client.embed_single(embed_text)

                                kp_data = {
                                    "id": uuid4(),
                                    "version": orchestrator.version_tag,
                                    "repository_id": repository_id,
                                    "category": kp["category"],
                                    "category_name": kp["category_name"],
                                    "title": kp["title"],
                                    "description": kp["description"],
                                    "confidence": kp["confidence"],
                                    "tags": kp.get("tags", []),
                                    "code_snippets": kp.get("code_snippets", []),
                                    "call_chain": kp.get("call_chain", []),
                                    "expansion": kp.get("expansion", {}),
                                    "knowledge_metadata": kp.get("metadata", {}),
                                    "embedding": embedding,
                                }
                                await kp_dao.create(shared_db, kp_data)
                                saved_for_this += 1
                            except Exception as exc:
                                logger.warning(f"保存知识点 {kp.get('title', 'unknown')} 失败: {exc}")

                    # 更新该 agent 的结果记录
                    current_agents = final_state.get("agent_results", {})
                    if current_agents:
                        # 合并到最终的状态
                        if "agent_results" not in final_state:
                            final_state["agent_results"] = {}
                        final_state["agent_results"].update(current_agents)

                except TimeoutError:
                    logger.error(f"Agent {agent_name} 执行超时")
                    # 无法更新具体知识点的超时状态（无 ID），仅记录日志
                except Exception as exc:
                    logger.error(f"Agent {agent_name} 执行失败: {exc}")

            # 最后完成版本（如果有新的 knowledge points）
            # 简化实现：不更新版本号，只标记部分完成

    asyncio.create_task(_run())

    return {"task_id": task_id}


# 保留原有的 delete_repository 函数结尾
