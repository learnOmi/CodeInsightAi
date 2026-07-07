"""
基础测试：验证 FastAPI 应用可以正常启动
"""

from fastapi.testclient import TestClient

from codeinsight.main import app

client = TestClient(app)


def test_health_check():
    """测试健康检查端点"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
