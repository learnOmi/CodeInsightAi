"""
Celery 应用工厂

创建并配置 Celery 实例，供 Worker 和 API 层共享。
"""

from celery import Celery

from codeinsight.config import settings


def make_celery(app_name: str = "codeinsight.tasks") -> Celery:
    """
    创建 Celery 实例

    Args:
        app_name: Celery 应用名称

    Returns:
        配置好的 Celery 实例
    """
    celery_app = Celery(app_name)

    celery_app.conf.update(
        broker_url=settings.redis_url,
        result_backend=settings.redis_url,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # 开发环境同步执行（直接调用而非走消息队列）
        task_always_eager=settings.celery_task_always_eager,
        # 任务超时（分析任务可能耗时较长）
        task_soft_time_limit=3600,   # 1 小时软超时
        task_time_limit=7200,         # 2 小时硬超时
        # 重试策略
        task_acks_late=True,          # 任务执行完再确认，保证失败可重试
        worker_prefetch_multiplier=1, # 每个 worker 一次只取一个任务
        # 队列路由
        task_default_queue="default",
        task_queues={
            "default": {"binding_key": "default"},
            "analysis": {"binding_key": "analysis.#"},
        },
        task_routes={
            "codeinsight.tasks.analysis_tasks.*": {"queue": "analysis"},
        },
    )

    # 发现同包下的所有任务模块
    celery_app.autodiscover_tasks(["codeinsight.tasks"])

    return celery_app


celery_app = make_celery()
