"""
失败节点 Redis 追踪

在分析过程中自动将失败的 AI 分析节点记录到 Redis，供前端轮询查询。
支持批量查询、清除、重试次数限制等操作。
"""

import json
import logging
from datetime import UTC, datetime

from codeinsight.db.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Redis key 前缀
FAILED_NODE_KEY_PREFIX = "failed_node:"
RETRY_COUNT_PREFIX = "retry_count:"
# 默认过期时间：24 小时
DEFAULT_TTL = 86400
# 单个类别的最大重试次数
MAX_RETRY_ATTEMPTS = 3


def _build_failed_node_key(repo_uuid: str) -> str:
    """构建某仓库的失败节点 Redis key"""
    return f"{FAILED_NODE_KEY_PREFIX}{repo_uuid}"


def _build_retry_count_key(repo_uuid: str) -> str:
    """构建某仓库的重试次数 Redis key"""
    return f"{RETRY_COUNT_PREFIX}{repo_uuid}"


def record_failed_node(repo_uuid: str, category: str, error: str, version: str | None = None) -> None:
    """
    记录一个失败的 AI 分析节点到 Redis

    使用 Redis Hash 存储：key 为 repo_uuid，field 为 category，
    value 为包含错误信息、版本、时间戳的 JSON 字符串。

    Args:
        repo_uuid: 仓库 UUID
        category: 失败的分析类别代码
        error: 错误信息
        version: 版本号（可选）
    """
    try:
        redis_client = get_redis_client()
        key = _build_failed_node_key(repo_uuid)
        value = json.dumps(
            {
                "category": category,
                "error": str(error),
                "version": version or "unknown",
                "failed_at": datetime.now(UTC).isoformat(),
            },
        )
        redis_client.hset(key, category, value)
        redis_client.expire(key, DEFAULT_TTL)
        logger.info("已记录失败节点: repo=%s, category=%s, error=%s", repo_uuid, category, error)
    except Exception as exc:
        logger.warning("记录失败节点到 Redis 失败: %s", exc)


def get_failed_nodes(repo_uuid: str) -> list[dict]:
    """
    获取某仓库所有失败的 AI 分析节点

    Args:
        repo_uuid: 仓库 UUID

    Returns:
        失败节点列表，每个元素包含 category、error、version、failed_at
    """
    try:
        redis_client = get_redis_client()
        key = _build_failed_node_key(repo_uuid)
        data = redis_client.hgetall(key)  # type: ignore[union-attr]
        if not data:
            return []

        result = []
        for category, value in data.items():  # type: ignore[union-attr]
            try:
                node_info = json.loads(value)
                node_info["category"] = category
                result.append(node_info)
            except (json.JSONDecodeError, TypeError):
                logger.warning("解析失败节点数据失败: repo=%s, category=%s", repo_uuid, category)
                result.append(
                    {
                        "category": category,
                        "error": str(value),
                        "version": "unknown",
                        "failed_at": "unknown",
                    }
                )

        return result
    except Exception as exc:
        logger.warning("获取失败节点失败: %s", exc)
        return []


def clear_failed_node(repo_uuid: str, category: str) -> None:
    """
    清除某个失败节点的记录（重试成功后调用）

    Args:
        repo_uuid: 仓库 UUID
        category: 分析类别代码
    """
    try:
        redis_client = get_redis_client()
        key = _build_failed_node_key(repo_uuid)
        redis_client.hdel(key, category)
        logger.info("已清除失败节点记录: repo=%s, category=%s", repo_uuid, category)
    except Exception as exc:
        logger.warning("清除失败节点记录失败: %s", exc)


def clear_all_failed_nodes(repo_uuid: str) -> None:
    """
    清除某仓库所有失败节点记录

    Args:
        repo_uuid: 仓库 UUID
    """
    try:
        redis_client = get_redis_client()
        key = _build_failed_node_key(repo_uuid)
        redis_client.delete(key)
        logger.info("已清除所有失败节点记录: repo=%s", repo_uuid)
    except Exception as exc:
        logger.warning("清除所有失败节点记录失败: %s", exc)


def get_retry_count(repo_uuid: str, category: str) -> int:
    """
    获取某仓库指定类别的重试次数

    Args:
        repo_uuid: 仓库 UUID
        category: 分析类别代码

    Returns:
        重试次数（0 表示从未重试过）
    """
    try:
        redis_client = get_redis_client()
        key = _build_retry_count_key(repo_uuid)
        count = redis_client.hget(key, category)  # type: ignore[union-attr]
        if count is None:
            return 0
        return int(count)  # type: ignore[arg-type]
    except Exception as exc:
        logger.warning("获取重试次数失败: %s", exc)
        return 0


def increment_retry_count(repo_uuid: str, category: str) -> int:
    """
    增加某仓库指定类别的重试次数

    Args:
        repo_uuid: 仓库 UUID
        category: 分析类别代码

    Returns:
        增加后的重试次数
    """
    try:
        redis_client = get_redis_client()
        key = _build_retry_count_key(repo_uuid)
        new_count = redis_client.hincrby(key, category, 1)  # type: ignore[misc]
        redis_client.expire(key, DEFAULT_TTL)
        return new_count  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("增加重试次数失败: %s", exc)
        return 0


def can_retry(repo_uuid: str, category: str) -> tuple[bool, int]:
    """
    检查某仓库指定类别是否还可以重试

    Args:
        repo_uuid: 仓库 UUID
        category: 分析类别代码

    Returns:
        (是否可以重试, 当前重试次数)
    """
    count = get_retry_count(repo_uuid, category)
    can = count < MAX_RETRY_ATTEMPTS
    return can, count
