"""
Amazon Q 模型 API
从 Amazon Q API 获取可用模型列表
"""
import logging
import httpx
from typing import List, Dict, Any
import os

logger = logging.getLogger(__name__)

# Amazon Q 支持的模型（根据 AWS 文档）
AMAZONQ_MODELS = [
    {
        "id": "claude-3.5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "owned_by": "anthropic"
    },
    {
        "id": "claude-3.7-sonnet",
        "name": "Claude 3.7 Sonnet",
        "owned_by": "anthropic"
    },
    {
        "id": "claude-4-sonnet",
        "name": "Claude 4 Sonnet",
        "owned_by": "anthropic"
    }
]


async def get_amazonq_models(access_token: str) -> List[Dict[str, Any]]:
    """
    从 Amazon Q API 获取可用模型列表
    
    Args:
        access_token: Amazon Q access token
        
    Returns:
        模型列表
    """
    # 目前 Amazon Q API 可能没有公开的模型列表端点
    # 根据 AWS 文档，支持的模型是固定的
    # 如果未来有 API 端点，可以在这里调用
    
    # 返回根据文档定义的模型列表
    return AMAZONQ_MODELS


def get_all_models() -> List[Dict[str, Any]]:
    """
    获取所有支持的模型列表（包括 OpenAI 兼容模型）
    
    Returns:
        模型列表
    """
    import time
    current_time = int(time.time())
    
    models = []
    
    # Amazon Q 原生模型
    for model in AMAZONQ_MODELS:
        models.append({
            "id": model["id"],
            "object": "model",
            "created": current_time,
            "owned_by": model["owned_by"],
            "permission": []
        })
    
    # 不再添加变体格式，只使用官方支持的三个模型
    
    # OpenAI 兼容模型
    openai_models = [
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4-turbo-preview",
        "gpt-4-0125-preview",
        "gpt-4-1106-preview",
        "gpt-4o",
        "gpt-4o-2024-05-13",
        "gpt-4o-mini",
        "gpt-4o-mini-2024-07-18",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
        "gpt-3.5-turbo-1106",
        "gpt-3.5-turbo-0125",
    ]
    
    for model_id in openai_models:
        models.append({
            "id": model_id,
            "object": "model",
            "created": current_time,
            "owned_by": "openai",
            "permission": []
        })
    
    return models

