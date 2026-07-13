"""
基础测试：验证 FastAPI 应用可以正常启动
"""

from fastapi.testclient import TestClient

from codeinsight.main import app

client = TestClient(app)


def test_health_check():
    """测试健康检查端点

    S-1 修复：端点不再返回敏感错误信息（错误时仅返回 "unavailable"）。
    注意：健康检查端点不加认证，因为需要被负载均衡器等基础设施访问。
    """
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["ok", "degraded"]
    assert "checks" in data
    assert "service" in data["checks"]
    assert "database" in data["checks"]
    assert "redis" in data["checks"]
    assert data["checks"]["service"]["status"] == "ok"
    assert "version" in data["checks"]["service"]
