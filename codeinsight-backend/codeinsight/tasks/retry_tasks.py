"""
单独重试 Celery 任务

用于对单个 AI 分析类别进行独立重试，只运行指定的节点，保留其他已成功的结果。
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from celery import shared_task

from codeinsight.agents.graph import CATEGORY_TO_NODE
from codeinsight.agents.graph import AnalysisGraph as AgentAnalysisGraph
from codeinsight.db.session import async_session_factory
from codeinsight.llm.client import LLMClient
from codeinsight.repositories import (
    AnalysisVersionDAO,
    AstNodeDAO,
    FileDAO,
    KnowledgePointDAO,
    RepositoryDAO,
)
from codeinsight.services.incremental_analyzer import IncrementalAnalyzer

logger = logging.getLogger(__name__)

# 重试类别的最大尝试次数
MAX_RETRY_ATTEMPTS = 3


@shared_task(
    name="tasks.retry_analysis_category",
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=3,
    default_retry_delay=10,
)
def retry_analysis_category(repo_uuid: str, category: str, force: bool = False) -> dict[str, Any]:
    """
    单独重试分析类别的 Celery 任务入口

    在同步上下文中调用异步函数。

    Args:
        repo_uuid: 仓库 UUID 字符串
        category: 分析类别代码（DP/AD/AL/ET/DK/TT/TK）
        force: 是否强制重试（即使已成功）

    Returns:
        包含 task_id、repo_id、category、knowledge_points_count 等字段的字典
    """
    return asyncio.run(_retry_analysis_category_async(repo_uuid, category, force))


async def _retry_analysis_category_async(repo_uuid: str, category: str, force: bool = False) -> dict[str, Any]:
    """异步执行单个类别的重试分析"""
    task_id = str(uuid.uuid4())
    repo_id = UUID(repo_uuid)

    # 验证类别代码
    node_name = CATEGORY_TO_NODE.get(category)
    if not node_name:
        raise ValueError(f"未知的类别代码: {category}")

    # 获取仓库信息
    repo_dao = RepositoryDAO()
    version_dao = AnalysisVersionDAO()
    ast_node_dao = AstNodeDAO()
    file_dao = FileDAO()
    kp_dao = KnowledgePointDAO()

    async with async_session_factory() as db:
        repo = await repo_dao.get_by_id(db, repo_id)
        if repo is None:
            raise ValueError(f"仓库不存在: {repo_id}")

        repo_path = repo.path
        logger.info(
            "开始重试分析: task_id=%s, repo_id=%s, category=%s, repo_path=%s", task_id, repo_id, category, repo_path
        )

        # 尝试获取最新已完成版本
        latest_version = await version_dao.get_latest_completed(db, repo_id)

        if latest_version is None:
            # 没有历史版本时，直接运行该 category（不保留旧结果）
            logger.info("无历史完成版本，直接运行 category: %s", category)
            new_version_tag = f"v{datetime.now(UTC).strftime('%Y%m%d')}-retry-{category}"
            return await _run_single_category(
                db=db,
                task_id=task_id,
                repo_id=repo_id,
                repo_path=repo_path,
                category=category,
                node_name=node_name,
                version_tag=new_version_tag,
                latest_version_label=None,
                version_dao=version_dao,
                ast_node_dao=ast_node_dao,
                file_dao=file_dao,
                kp_dao=kp_dao,
                existing_kp_count=0,
            )

        # 检查该类别在当前版本中的状态
        agent_status = latest_version.agent_status or {}
        category_status = agent_status.get(category, {})
        current_status = category_status.get("status", "")

        if current_status == "success" and not force:
            return {
                "task_id": task_id,
                "repo_id": str(repo_id),
                "category": category,
                "status": "skipped",
                "message": f"该类别已成功（version={latest_version.version}），设置 force=true 可强制重试",
                "existing_kp_count": category_status.get("knowledge_points_count", 0),
            }

        # 构建重试版本号
        new_version_tag = f"{latest_version.version}-retry-{category}"

        # 加载该类别在历史版本中的知识点
        existing_kps = await kp_dao.list(db, repo_id, version=latest_version.version, category=category)
        existing_kp_count = len(existing_kps)

        logger.info(
            "重试分析: version=%s, category=%s, existing_kp_count=%d, existing_status=%s",
            latest_version.version,
            category,
            existing_kp_count,
            current_status,
        )

        # 如果类别已存在数据，先清理该 category 的旧知识点（避免重复）
        if existing_kp_count > 0:
            deleted = await kp_dao.delete_by_version_and_category(db, repo_id, latest_version.version, category)
            logger.info("重试前清理旧知识点: category=%s, deleted=%d", category, deleted)

        return await _run_single_category(
            db=db,
            task_id=task_id,
            repo_id=repo_id,
            repo_path=repo_path,
            category=category,
            node_name=node_name,
            version_tag=new_version_tag,
            latest_version_label=latest_version.version,
            version_dao=version_dao,
            ast_node_dao=ast_node_dao,
            file_dao=file_dao,
            kp_dao=kp_dao,
            existing_kp_count=existing_kp_count,
        )


async def _run_single_category(
    *,
    db: Any,
    task_id: str,
    repo_id: UUID,
    repo_path: str,
    category: str,
    node_name: str,
    version_tag: str,
    latest_version_label: str | None,
    version_dao: AnalysisVersionDAO,
    ast_node_dao: AstNodeDAO,
    file_dao: FileDAO,
    kp_dao: KnowledgePointDAO,
    existing_kp_count: int,
) -> dict[str, Any]:
    """
    运行单个分析类别的完整流程

    增量模式（latest_version_label 不为空时）：
    1. 使用 IncrementalAnalyzer 计算变更文件集（含依赖传播）
    2. 仅加载变更文件的代码片段和 AST 数据
    3. 执行 AgentGraph（仅目标节点），只分析变更文件
    4. 存储知识点 + 保留未变更文件的历史知识点

    Args:
        db: 数据库会话
        task_id: 任务唯一标识
        repo_id: 仓库 UUID
        repo_path: 仓库路径
        category: 分析类别代码
        node_name: 节点名称
        version_tag: 新版本号标签
        latest_version_label: 上一次分析的版本标签（None 表示全量重试）
        version_dao: 版本 DAO
        ast_node_dao: AST 节点 DAO
        file_dao: 文件 DAO
        kp_dao: 知识点 DAO
        existing_kp_count: 已有知识点数量

    Returns:
        重试结果字典
    """
    # 加载所有文件
    all_files = await file_dao.get_by_repository(db, repo_id)

    # 增量分析：计算变更文件集
    if latest_version_label:
        analyzer = IncrementalAnalyzer()
        diff = await analyzer.compute_diff(repo_id, all_files, latest_version_label, db=db)

        # 判断是否需要降级为全量
        needs_full = diff.needs_full_analysis
        if needs_full:
            logger.warning(
                "增量分析降级为全量: repo=%s, category=%s, 变更文件占比过大",
                repo_id,
                category,
            )

        # 获取需要分析的文件
        files_to_analyze = all_files if needs_full else await analyzer.get_files_to_analyze(diff, all_files)

        # 获取受影响的文件路径集合（用于过滤 AST 数据）
        affected_paths = {c.path for c in diff.changed_files}
        affected_paths.update(diff.propagated_files)

        logger.info(
            "增量重试: repo=%s, category=%s, changed=%d, propagated=%d, analyze_files=%d, skip_files=%d, needs_full=%s",
            repo_id,
            category,
            len(diff.changed_files),
            len(diff.propagated_files),
            len(files_to_analyze),
            diff.skipped_files,
            needs_full,
        )
    else:
        files_to_analyze = all_files
        affected_paths = None  # None 表示全量
        logger.info("全量重试: repo=%s, category=%s, files=%d", repo_id, category, len(all_files))

    # 加载 AST 节点数据（仅保留受影响文件的 AST）
    all_ast_nodes = await ast_node_dao.get_by_repository(db, repo_id)
    if affected_paths is not None:
        affected_ast_nodes = [n for n in all_ast_nodes if n.file_path in affected_paths]
    else:
        affected_ast_nodes = all_ast_nodes

    ast_data = [
        {
            "id": str(n.id),
            "node_type": n.node_type,
            "name": n.name,
            "file_id": str(n.file_id),
            "start_line": n.start_line,
            "end_line": n.end_line,
            "qualified_name": n.qualified_name,
        }
        for n in affected_ast_nodes
    ]

    # 读取变更文件的代码内容
    code_snippets = []
    for f in files_to_analyze:
        try:
            file_path = Path(repo_path) / f.path if repo_path else Path(f.absolute_path)
            content = file_path.read_text(encoding="utf-8", errors="replace")
            code_snippets.append({"file_path": f.path, "code": content[:5000]})
        except Exception as exc:
            logger.warning("读取文件失败: repo=%s, path=%s, error=%s", repo_id, f.path, exc)

    # 代码库规模检测
    enable_chunking = len(all_files) > 2000

    logger.info(
        "准备重试分析: repo_id=%s, category=%s, ast_nodes=%d, snippets=%d, version_tag=%s",
        repo_id,
        category,
        len(ast_data),
        len(code_snippets),
        version_tag,
    )

    # 创建初始状态
    initial_state = AgentAnalysisGraph.create_initial_state(
        repo_id=str(repo_id),
        ast_data=ast_data,
        code_snippets=code_snippets,
        category=category,
        enable_chunking=enable_chunking,
    )

    # 执行 AgentGraph
    llm_client = LLMClient()
    agent_graph = AgentAnalysisGraph(llm_client)
    final_state = await agent_graph.run(initial_state)

    knowledge_points = final_state.get("knowledge_points", []) if final_state else []
    agent_results = final_state.get("agent_results", {}) if final_state else {}
    knowledge_points_count = len(knowledge_points)

    logger.info(
        "重试分析完成: task_id=%s, repo_id=%s, category=%s, new_kp_count=%d",
        task_id,
        repo_id,
        category,
        knowledge_points_count,
    )

    # 存储新知识点到数据库
    if knowledge_points:
        try:
            kps_to_create = []
            for kp in knowledge_points:
                kp_data = {
                    "repository_id": repo_id,
                    "version": version_tag,
                    "category": kp.get("category", category),
                    "category_name": kp.get("category_name", ""),
                    "title": kp.get("title", ""),
                    "description": kp.get("description", ""),
                    "confidence": kp.get("confidence", 0.5),
                    "tags": kp.get("tags", []),
                    "code_snippets": kp.get("code_snippets", []),
                    "call_chain": kp.get("call_chain", []),
                    "expansion": kp.get("expansion", {}),
                    "knowledge_metadata": kp.get("metadata", {}),
                }
                kps_to_create.append(kp_data)

            created = await kp_dao.batch_create(db, kps_to_create)
            logger.info("重试知识点已存储: count=%d", len(created))

            # 同步到 Meilisearch
            try:
                from codeinsight.services.meilisearch_client import MeiliSearchClient

                meili_client = MeiliSearchClient()
                meili_client.add_documents(knowledge_points)
            except Exception as exc:
                logger.warning("重试知识点同步 Meilisearch 失败: %s", exc)
        except Exception as exc:
            logger.error("重试知识点存储失败: %s", exc, exc_info=True)
            raise

    # 更新版本记录的 agent_status
    new_agent_status = agent_results or {}
    if category in new_agent_status:
        new_agent_status[category]["timestamp"] = datetime.now(UTC).isoformat()
        new_agent_status[category]["knowledge_points_count"] = knowledge_points_count
    else:
        new_agent_status[category] = {
            "status": "success" if knowledge_points else "failed",
            "attempts": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "knowledge_points_count": knowledge_points_count,
        }

    # 更新 agent_status：使用 version_tag 精确查找当前重试版本，
    # 而不是 get_latest_completed（会命中上一个版本）
    async with async_session_factory() as db2:
        current_version = await version_dao.get_by_version_tag(db2, repo_id, version_tag)
        if current_version is None:
            # 降级：尝试查找该 repo 的最新版本
            current_version = await version_dao.get_latest_completed(db2, repo_id)
        if current_version:
            try:
                await version_dao.update(db2, current_version.id, {"agent_status": new_agent_status})
                await db2.commit()
                logger.info("已更新版本 agent_status: version=%s, category=%s", current_version.version, category)

                # 重试成功后清除 Redis 中的失败节点记录
                if knowledge_points:
                    try:
                        from codeinsight.db.redis_failed_nodes import clear_failed_node

                        clear_failed_node(str(repo_id), category)
                        logger.info("已清除失败节点记录: repo=%s, category=%s", repo_id, category)
                    except Exception as exc:
                        logger.warning("清除失败节点记录失败: %s", exc)
            except Exception as exc:
                logger.warning("更新版本 agent_status 失败: %s", exc, exc_info=True)

    return {
        "task_id": task_id,
        "repo_id": str(repo_id),
        "category": category,
        "node_name": node_name,
        "knowledge_points_count": knowledge_points_count,
        "version_tag": version_tag,
        "agent_results": new_agent_status,
        "status": "success" if knowledge_points else "failed",
        "incremental": latest_version_label is not None,
    }


@shared_task(
    name="tasks.retry_expansion_task",
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=3,
    default_retry_delay=10,
)
def retry_expansion_task(repo_uuid: str, version_id: str, kp_ids: list[str]) -> dict[str, Any]:
    """
    重试拓展知识生成任务

    对指定知识点重新生成拓展内容。

    Args:
        repo_uuid: 仓库 UUID 字符串
        version_id: 分析版本 ID 字符串
        kp_ids: 知识点 ID 列表

    Returns:
        任务结果字典
    """
    task_id = str(uuid.uuid4())
    logger.info(
        "开始重试拓展知识生成: repo=%s, version=%s, kps=%d, task_id=%s", repo_uuid, version_id, len(kp_ids), task_id
    )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_async_retry_expansion(repo_uuid, version_id, kp_ids))
        loop.close()
        return result
    except Exception as exc:
        logger.error("重试拓展知识生成失败: %s", exc, exc_info=True)
        return {"task_id": task_id, "status": "failed", "error": str(exc)}


async def _async_retry_expansion(repo_uuid: str, version_id: str, kp_ids: list[str]) -> dict[str, Any]:
    """
    异步执行拓展知识重试

    Args:
        repo_uuid: 仓库 UUID
        version_id: 分析版本 ID
        kp_ids: 知识点 ID 列表

    Returns:
        任务结果
    """
    from codeinsight.agents.node import ExpansionNode
    from codeinsight.llm.client import LLMClient

    _repo_id = UUID(repo_uuid)
    llm_client = LLMClient()
    expansion_node = ExpansionNode(llm_client=llm_client)

    logger.info("异步重试拓展知识生成: repo=%s, kps=%d", repo_uuid, len(kp_ids))

    async with async_session_factory() as db:
        kp_dao = KnowledgePointDAO()
        version_dao = AnalysisVersionDAO()

        success_count = 0
        fail_count = 0

        for kp_id_str in kp_ids:
            try:
                kp = await kp_dao.get_by_id(db, UUID(kp_id_str))
                if kp is None:
                    logger.warning("知识点不存在: id=%s", kp_id_str)
                    fail_count += 1
                    continue

                # 构建知识点的 dict 格式
                kp_dict = {
                    "title": kp.title,
                    "category": kp.category,
                    "category_name": kp.category_name,
                    "description": kp.description,
                    "confidence": kp.confidence,
                    "tags": kp.tags or [],
                    "code_snippets": kp.code_snippets or [],
                    "call_chain": kp.call_chain or [],
                    "expansion": kp.expansion or {},
                    "metadata": kp.knowledge_metadata or {},
                }

                # 生成拓展内容
                expansion = await expansion_node._generate_expansion(kp_dict)
                if expansion:
                    # 更新数据库
                    await kp_dao.update(db, kp.id, {"expansion": expansion})
                    success_count += 1
                    logger.info("拓展内容重试成功: title=%s", kp.title)
                else:
                    fail_count += 1
                    logger.warning("拓展内容重试失败: title=%s", kp.title)
            except Exception as exc:
                fail_count += 1
                logger.warning("拓展内容重试异常: id=%s, error=%s", kp_id_str, exc)

        # 清理并更新版本状态
        if success_count > 0:
            await db.commit()

            # 更新 agent_status 中 _expansion 的状态
            version = await version_dao.get_by_id(db, UUID(version_id))
            if version:
                agent_status = version.agent_status or {}
                expansion_status = agent_status.get("_expansion", {})
                expansion_status["status"] = "success" if fail_count == 0 else "partial_failure"
                expansion_status["retry_count"] = expansion_status.get("retry_count", 0) + 1
                expansion_status["last_retry"] = datetime.now(UTC).isoformat()
                agent_status["_expansion"] = expansion_status
                await version_dao.update(db, UUID(version_id), {"agent_status": agent_status})
                await db.commit()

        logger.info("重试拓展知识生成完成: success=%d, fail=%d", success_count, fail_count)
        return {
            "task_id": str(uuid.uuid4()),
            "status": "success" if success_count > 0 else "failed",
            "success_count": success_count,
            "fail_count": fail_count,
        }
