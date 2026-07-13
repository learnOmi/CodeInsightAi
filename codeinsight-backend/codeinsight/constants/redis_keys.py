"""
Redis 键命名常量

集中管理所有 Redis 键模式，避免硬编码散落在业务代码中（D-2 修复）。
所有键使用命名空间分隔符 `:` 组织，格式为：{namespace}:{id}:{field}。
"""

# ---- 分析任务相关 ----
# 格式: task:{task_id}:repo     → 任务 → 仓库映射
# 格式: task:{task_id}:mode     → 任务分析模式
# 格式: task:{task_id}:cancel   → 取消标志

TASK_REPO_KEY = "task:{task_id}:repo"
TASK_MODE_KEY = "task:{task_id}:mode"
TASK_CANCEL_KEY = "task:{task_id}:cancel"


# ---- 仓库相关 ----
# 格式: repo:{repository_id}:active_task → 仓库当前活跃任务 ID

REPO_ACTIVE_TASK_KEY = "repo:{repository_id}:active_task"


# ---- 键构建器（返回可直接传给 Redis get/set/delete 的字符串） ----


def task_repo_key(task_id: str) -> str:
    """获取 task_id → repository_id 映射的 Redis 键"""
    return TASK_REPO_KEY.format(task_id=task_id)


def task_mode_key(task_id: str) -> str:
    """获取 task_id → analysis mode 映射的 Redis 键"""
    return TASK_MODE_KEY.format(task_id=task_id)


def task_cancel_key(task_id: str) -> str:
    """获取 task_id 取消标志的 Redis 键"""
    return TASK_CANCEL_KEY.format(task_id=task_id)


def repo_active_task_key(repository_id: str) -> str:
    """获取 repository_id → active task_id 映射的 Redis 键"""
    return REPO_ACTIVE_TASK_KEY.format(repository_id=repository_id)
