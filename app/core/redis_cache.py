"""
Redis 缓存模块
用于缓存 token 和其他数据
"""
import json
import logging
from typing import Optional, Any
from datetime import datetime, timedelta
import redis
from redis.exceptions import ConnectionError, RedisError

logger = logging.getLogger(__name__)

# Redis 连接实例
_redis_client: Optional[redis.Redis] = None
_redis_available: bool = False


def init_redis():
    """初始化 Redis 连接"""
    global _redis_client, _redis_available
    
    try:
        import os
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD", None)
        
        _redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2
        )
        
        # 测试连接
        _redis_client.ping()
        _redis_available = True
        logger.info(f"Redis 连接成功: {redis_host}:{redis_port}/{redis_db}")
    except (ConnectionError, RedisError, Exception) as e:
        _redis_available = False
        logger.warning(f"Redis 不可用，将使用文件缓存: {e}")
        _redis_client = None


def is_redis_available() -> bool:
    """检查 Redis 是否可用"""
    if not _redis_available or not _redis_client:
        return False
    try:
        _redis_client.ping()
        return True
    except:
        return False


def get_token_cache(account_id: str) -> Optional[dict]:
    """
    从 Redis 获取 token 缓存
    
    Args:
        account_id: 账号 ID
        
    Returns:
        token 缓存字典，包含 access_token, refresh_token, expires_at
    """
    if not is_redis_available():
        return None
    
    try:
        key = f"token:account:{account_id}"
        data = _redis_client.get(key)
        if data:
            cache = json.loads(data)
            # 检查是否过期
            if 'expires_at' in cache:
                expires_at = datetime.fromisoformat(cache['expires_at'])
                if datetime.now() < expires_at:
                    return cache
                else:
                    # 过期了，删除
                    _redis_client.delete(key)
    except Exception as e:
        logger.error(f"从 Redis 获取 token 缓存失败: {e}")
    
    return None


def set_token_cache(account_id: str, access_token: str, refresh_token: Optional[str], expires_at: datetime):
    """
    保存 token 到 Redis
    
    Args:
        account_id: 账号 ID
        access_token: 访问令牌
        refresh_token: 刷新令牌（可选）
        expires_at: 过期时间
    """
    if not is_redis_available():
        return
    
    try:
        key = f"token:account:{account_id}"
        cache = {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at.isoformat()
        }
        
        # 计算 TTL（秒），加上一些缓冲时间
        ttl = int((expires_at - datetime.now()).total_seconds()) + 300  # 额外5分钟缓冲
        
        _redis_client.setex(key, ttl, json.dumps(cache))
        logger.debug(f"Token 已缓存到 Redis: {key}")
    except Exception as e:
        logger.error(f"保存 token 到 Redis 失败: {e}")


def delete_token_cache(account_id: str):
    """删除 token 缓存"""
    if not is_redis_available():
        return
    
    try:
        key = f"token:account:{account_id}"
        _redis_client.delete(key)
    except Exception as e:
        logger.error(f"从 Redis 删除 token 缓存失败: {e}")


def get(key: str) -> Optional[Any]:
    """从 Redis 获取值"""
    if not is_redis_available():
        return None
    
    try:
        data = _redis_client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"从 Redis 获取值失败: {e}")
    
    return None


def set(key: str, value: Any, ttl: Optional[int] = None):
    """
    设置 Redis 值
    
    Args:
        key: 键
        value: 值
        ttl: 过期时间（秒），None 表示不过期
    """
    if not is_redis_available():
        return
    
    try:
        data = json.dumps(value)
        if ttl:
            _redis_client.setex(key, ttl, data)
        else:
            _redis_client.set(key, data)
    except Exception as e:
        logger.error(f"设置 Redis 值失败: {e}")


def delete(key: str):
    """删除 Redis 键"""
    if not is_redis_available():
        return
    
    try:
        _redis_client.delete(key)
    except Exception as e:
        logger.error(f"删除 Redis 键失败: {e}")

