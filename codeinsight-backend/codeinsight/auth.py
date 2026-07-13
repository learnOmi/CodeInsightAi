"""
认证模块

提供 API Key 认证和 JWT Token 认证支持。
当前阶段使用 API Key 认证（无需用户系统），后续可升级为完整 JWT 方案。
"""

import hmac
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer


class APIKeyAuth:
    """
    API Key 认证

    从请求头 X-API-Key 中读取密钥并验证。
    """

    def __init__(self, valid_key: str | None):
        self.valid_key = valid_key

    def authenticate(self, key_header: str | None) -> None:
        """验证 API Key"""
        if not key_header or not self.valid_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid API key",
                headers={"WWW-Authenticate": "APIKey"},
            )
        # 使用常量时间比较防止时序攻击
        if not hmac.compare_digest(key_header, self.valid_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "APIKey"},
            )


# API Key 头部定义
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Annotated 类型别名：API Key 依赖
ApiKeyDep = Annotated[str | None, Security(api_key_header)]


# Bearer Token 定义（预留，供后续 JWT 方案使用）
bearer_scheme = HTTPBearer(auto_error=False)

# Annotated 类型别名：Bearer Token 依赖
BearerTokenDep = Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)]


def get_api_key_dependency(valid_key: str | None):
    """
    创建 API Key 认证依赖

    Args:
        valid_key: 有效的 API Key，为 None 时跳过认证（开发环境）

    Returns:
        认证依赖函数
    """

    def _check_api_key(key: ApiKeyDep):
        if valid_key is None:
            # 开发环境，跳过认证
            return None
        APIKeyAuth(valid_key).authenticate(key)
        return None

    return _check_api_key


def get_bearer_token_dependency(valid_secret: str | None):
    """
    创建 Bearer Token 认证依赖（JWT 预留）

    当前阶段不使用，后续集成用户系统后启用。

    Args:
        valid_secret: JWT 密钥，为 None 时跳过认证

    Returns:
        认证依赖函数
    """

    def _check_bearer_token(token: BearerTokenDep):
        if valid_secret is None:
            return None
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # TODO: 集成用户系统后，使用 python-jose 验证 JWT
        # 当前仅检查 token 非空
        if not token.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return token.credentials

    return _check_bearer_token
