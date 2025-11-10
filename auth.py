"""
认证模块
负责 Token 刷新和管理
"""
import httpx
import logging
from typing import Optional, Dict, Any
from config import read_global_config, update_global_config

logger = logging.getLogger(__name__)


class TokenRefreshError(Exception):
    """Token 刷新失败异常"""
    pass


async def refresh_token_for_account(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token_endpoint: Optional[str] = None,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    为指定账号刷新 access_token（用于账号池模式）
    支持 Redis 缓存

    Args:
        refresh_token: 账号的刷新令牌
        client_id: 客户端 ID
        client_secret: 客户端密钥
        token_endpoint: Token 端点 URL（可选，默认使用配置中的值）
        account_id: 账号 ID（用于 Redis 缓存）

    Returns:
        Dict[str, Any]: 包含 access_token, refresh_token, expires_in 的字典

    Raises:
        TokenRefreshError: 刷新失败时抛出异常
    """
    # 尝试从 Redis 获取缓存的 token
    if account_id:
        from app.core.redis_cache import get_token_cache
        cached_token = get_token_cache(account_id)
        if cached_token:
            logger.info(f"从 Redis 缓存获取账号 {account_id} 的 token")
            from datetime import datetime
            expires_at = datetime.fromisoformat(cached_token['expires_at'])
            # 检查是否还有效（提前5分钟刷新）
            if datetime.now() < (expires_at - timedelta(minutes=5)):
                return {
                    "access_token": cached_token['access_token'],
                    "refresh_token": cached_token.get('refresh_token'),
                    "expires_in": int((expires_at - datetime.now()).total_seconds())
                }
    
    try:
        # 如果没有提供 token_endpoint，从配置中读取
        if not token_endpoint:
            config = await read_global_config()
            token_endpoint = config.token_endpoint

        logger.info("开始刷新账号 access_token")

        # 构建并发送请求
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            payload = {
                "grantType": "refresh_token",
                "refreshToken": refresh_token,
                "clientId": client_id,
                "clientSecret": client_secret
            }

            # 构建 AWS SDK 风格的请求头（完整版本）
            import uuid
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "aws-sdk-rust/1.3.9 os/macos lang/rust/1.87.0",
                "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/ssooidc/1.88.0 os/macos lang/rust/1.87.0 m/E app/AmazonQ-For-CLI",
                "Amz-Sdk-Request": "attempt=1; max=3",
                "Amz-Sdk-Invocation-Id": str(uuid.uuid4()),
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br"
            }

            response = await http_client.post(
                token_endpoint,
                json=payload,
                headers=headers
            )

            # 检查 HTTP 错误
            response.raise_for_status()

            # 解析响应
            response_data = response.json()

            # 提取 token 信息（使用驼峰命名）
            new_access_token = response_data.get("accessToken")
            new_refresh_token = response_data.get("refreshToken")
            expires_in = response_data.get("expiresIn")

            if not new_access_token:
                raise TokenRefreshError("响应中缺少 access_token")

            logger.info("账号 Token 刷新成功")
            
            # 保存到 Redis 缓存
            if account_id:
                from app.core.redis_cache import set_token_cache
                from datetime import datetime, timedelta
                expires_at = datetime.now() + timedelta(seconds=int(expires_in) if expires_in else 3600)
                set_token_cache(account_id, new_access_token, new_refresh_token, expires_at)
            
            return {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": int(expires_in) if expires_in else 3600
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"Token 刷新失败 - HTTP 错误: {e.response.status_code} {e.response.text}")
        raise TokenRefreshError(f"HTTP 错误: {e.response.status_code}") from e
    except httpx.RequestError as e:
        logger.error(f"Token 刷新失败 - 网络错误: {str(e)}")
        raise TokenRefreshError(f"网络错误: {str(e)}") from e
    except Exception as e:
        logger.error(f"Token 刷新失败 - 未知错误: {str(e)}")
        raise TokenRefreshError(f"未知错误: {str(e)}") from e


async def refresh_token() -> bool:
    """
    刷新 access_token（使用全局配置）

    Returns:
        bool: 刷新成功返回 True，失败返回 False

    Raises:
        TokenRefreshError: 刷新失败时抛出异常
    """
    try:
        # 步骤 1: 读取配置
        config = await read_global_config()

        logger.info("开始刷新 access_token")

        # 步骤 2: 构建并发送请求
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            payload = {
                "grantType": "refresh_token",
                "refreshToken": config.refresh_token,
                "clientId": config.client_id,
                "clientSecret": config.client_secret
            }

            # 构建 AWS SDK 风格的请求头（完整版本）
            import uuid
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "aws-sdk-rust/1.3.9 os/macos lang/rust/1.87.0",
                "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/ssooidc/1.88.0 os/macos lang/rust/1.87.0 m/E app/AmazonQ-For-CLI",
                "Amz-Sdk-Request": "attempt=1; max=3",
                "Amz-Sdk-Invocation-Id": "362523fb-ad17-428a-b3be-5a812faf0448",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br"
            }

            response = await http_client.post(
                config.token_endpoint,
                json=payload,
                headers=headers
            )

            # 检查 HTTP 错误
            response.raise_for_status()

            # 步骤 3: 解析响应并更新配置
            response_data = response.json()

            # 提取 token 信息（使用驼峰命名）
            new_access_token = response_data.get("accessToken")
            new_refresh_token = response_data.get("refreshToken")
            expires_in = response_data.get("expiresIn")

            if not new_access_token:
                raise TokenRefreshError("响应中缺少 access_token")

            # 更新全局配置
            await update_global_config(
                access_token=new_access_token,
                refresh_token=new_refresh_token if new_refresh_token else None,
                expires_in=int(expires_in) if expires_in else 3600  # 默认 1 小时
            )

            logger.info("Token 刷新成功")
            return True

    except httpx.HTTPStatusError as e:
        logger.error(f"Token 刷新失败 - HTTP 错误: {e.response.status_code} {e.response.text}")
        raise TokenRefreshError(f"HTTP 错误: {e.response.status_code}") from e
    except httpx.RequestError as e:
        logger.error(f"Token 刷新失败 - 网络错误: {str(e)}")
        raise TokenRefreshError(f"网络错误: {str(e)}") from e
    except Exception as e:
        logger.error(f"Token 刷新失败 - 未知错误: {str(e)}")
        raise TokenRefreshError(f"未知错误: {str(e)}") from e


async def ensure_valid_token() -> str:
    """
    确保有有效的 access_token
    如果 token 过期或不存在，则自动刷新

    Returns:
        str: 有效的 access_token

    Raises:
        TokenRefreshError: 无法获取有效 token 时抛出异常
    """
    config = await read_global_config()

    # 检查 token 是否过期
    if config.is_token_expired():
        logger.info("Token 已过期或不存在，开始刷新")
        await refresh_token()
        # 重新读取配置获取新 token
        config = await read_global_config()

    if not config.access_token:
        raise TokenRefreshError("无法获取有效的 access_token")

    return config.access_token


async def get_auth_headers() -> Dict[str, str]:
    """
    获取包含认证信息的请求头（仅 Authorization）

    Returns:
        Dict[str, str]: 包含 Authorization 的请求头
    """
    access_token = await ensure_valid_token()
    return {
        "Authorization": f"Bearer {access_token}"
    }