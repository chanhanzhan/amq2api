"""
主服务模块
FastAPI 服务器，提供 Claude API 兼容的接口
"""
import logging
import httpx
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

from config import read_global_config, get_config_sync
from auth import get_auth_headers
from models import ClaudeRequest
from converter import convert_claude_to_codewhisperer_request, codewhisperer_request_to_dict
from stream_handler_new import handle_amazonq_stream
from message_processor import process_claude_history_for_amazonq, log_history_summary

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化配置
    logger.info("正在初始化配置...")
    try:
        await read_global_config()
        logger.info("配置初始化成功")
    except Exception as e:
        logger.error(f"配置初始化失败: {e}")
        raise

    yield

    # 关闭时清理资源
    logger.info("正在关闭服务...")


# 创建 FastAPI 应用
app = FastAPI(
    title="Amazon Q to Claude API Proxy",
    description="将 Claude API 请求转换为 Amazon Q/CodeWhisperer 请求的代理服务",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "Amazon Q to Claude API Proxy",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """健康检查端点"""
    try:
        config = get_config_sync()
        return {
            "status": "healthy",
            "has_token": config.access_token is not None,
            "token_expired": config.is_token_expired()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.get("/v1/models")
async def list_models():
    """
    列出可用的模型（OpenAI API 兼容）
    返回支持的 Claude 模型列表
    """
    import time
    
    current_time = int(time.time())
    
    return {
        "object": "list",
        "data": [
            {
                "id": "claude-sonnet-4.5",
                "object": "model",
                "created": current_time,
                "owned_by": "anthropic",
                "permission": [],
                "root": "claude-sonnet-4.5",
                "parent": None
            },
            {
                "id": "claude-sonnet-4",
                "object": "model",
                "created": current_time,
                "owned_by": "anthropic",
                "permission": [],
                "root": "claude-sonnet-4",
                "parent": None
            },
            {
                "id": "claude-3-5-sonnet-20241022",
                "object": "model",
                "created": current_time,
                "owned_by": "anthropic",
                "permission": [],
                "root": "claude-3-5-sonnet-20241022",
                "parent": None
            }
        ]
    }


@app.post("/v1/messages")
async def create_message(request: Request):
    """
    Claude API 兼容的消息创建端点
    接收 Claude 格式的请求，转换为 CodeWhisperer 格式并返回流式响应
    """
    try:
        # 解析请求体
        request_data = await request.json()

        # 标准 Claude API 格式 - 转换为 conversationState
        logger.info(f"收到标准 Claude API 请求: {request_data.get('model', 'unknown')}")

        # 转换为 ClaudeRequest 对象
        claude_req = parse_claude_request(request_data)

        # 获取配置
        config = await read_global_config()

        # 转换为 CodeWhisperer 请求
        codewhisperer_req = convert_claude_to_codewhisperer_request(
            claude_req,
            conversation_id=None,  # 自动生成
            profile_arn=config.profile_arn
        )

        # 转换为字典
        codewhisperer_dict = codewhisperer_request_to_dict(codewhisperer_req)
        model = claude_req.model

        # 处理历史记录：合并连续的 userInputMessage
        conversation_state = codewhisperer_dict.get("conversationState", {})
        history = conversation_state.get("history", [])

        if history:
            # 记录原始历史记录
            logger.info("=" * 80)
            logger.info("原始历史记录:")
            log_history_summary(history, prefix="[原始] ")

            # 合并连续的用户消息
            processed_history = process_claude_history_for_amazonq(history)

            # 记录处理后的历史记录
            logger.info("=" * 80)
            logger.info("处理后的历史记录:")
            log_history_summary(processed_history, prefix="[处理后] ")

            # 更新请求体
            conversation_state["history"] = processed_history
            codewhisperer_dict["conversationState"] = conversation_state

        # 处理 currentMessage 中的重复 toolResults（标准 Claude API 格式）
        conversation_state = codewhisperer_dict.get("conversationState", {})
        current_message = conversation_state.get("currentMessage", {})
        user_input_message = current_message.get("userInputMessage", {})
        user_input_message_context = user_input_message.get("userInputMessageContext", {})

        # 合并 currentMessage 中重复的 toolResults
        tool_results = user_input_message_context.get("toolResults", [])
        if tool_results:
            merged_tool_results = []
            seen_tool_use_ids = set()

            for result in tool_results:
                tool_use_id = result.get("toolUseId")
                if tool_use_id in seen_tool_use_ids:
                    # 找到已存在的条目，合并 content
                    for existing in merged_tool_results:
                        if existing.get("toolUseId") == tool_use_id:
                            existing["content"].extend(result.get("content", []))
                            logger.info(f"[CURRENT MESSAGE - CLAUDE API] 合并重复的 toolUseId {tool_use_id} 的 content")
                            break
                else:
                    # 新条目
                    seen_tool_use_ids.add(tool_use_id)
                    merged_tool_results.append(result)

            user_input_message_context["toolResults"] = merged_tool_results
            user_input_message["userInputMessageContext"] = user_input_message_context
            current_message["userInputMessage"] = user_input_message
            conversation_state["currentMessage"] = current_message
            codewhisperer_dict["conversationState"] = conversation_state

        final_request = codewhisperer_dict

        # 调试：打印请求体
        import json
        logger.info(f"转换后的请求体: {json.dumps(final_request, indent=2, ensure_ascii=False)}")

        # 获取认证头
        base_auth_headers = await get_auth_headers()

        # 构建 Amazon Q 特定的请求头（完整版本）
        import uuid
        auth_headers = {
            **base_auth_headers,
            "Content-Type": "application/x-amz-json-1.0",
            "X-Amz-Target": "AmazonCodeWhispererStreamingService.GenerateAssistantResponse",
            "User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 md/appVersion-1.19.3 app/AmazonQ-For-CLI",
            "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 m/F app/AmazonQ-For-CLI",
            "X-Amzn-Codewhisperer-Optout": "true",
            "Amz-Sdk-Request": "attempt=1; max=3",
            "Amz-Sdk-Invocation-Id": str(uuid.uuid4()),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br"
        }

        # 发送请求到 Amazon Q
        logger.info("正在发送请求到 Amazon Q...")

        # API URL（根路径，不需要额外路径）
        config = await read_global_config()
        api_url = config.api_endpoint.rstrip('/')

        # 创建字节流响应
        async def byte_stream():
            async with httpx.AsyncClient(timeout=300.0) as client:
                try:
                    async with client.stream(
                        "POST",
                        api_url,
                        json=final_request,
                        headers=auth_headers
                    ) as response:
                        # 检查响应状态
                        if response.status_code != 200:
                            error_text = await response.aread()
                            logger.error(f"上游 API 错误: {response.status_code} {error_text}")
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"上游 API 错误: {error_text.decode()}"
                            )

                        # 处理 Event Stream（字节流）
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                yield chunk

                except httpx.RequestError as e:
                    logger.error(f"请求错误: {e}")
                    raise HTTPException(status_code=502, detail=f"上游服务错误: {str(e)}")

        # 返回流式响应
        async def claude_stream():
            async for event in handle_amazonq_stream(byte_stream(), model=model, request_data=request_data):
                yield event

        return StreamingResponse(
            claude_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理请求时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


def parse_claude_request(data: dict) -> ClaudeRequest:
    """
    解析 Claude API 请求数据

    Args:
        data: 请求数据字典

    Returns:
        ClaudeRequest: Claude 请求对象
    """
    from models import ClaudeMessage, ClaudeTool

    # 解析消息
    messages = []
    for msg in data.get("messages", []):
        messages.append(ClaudeMessage(
            role=msg["role"],
            content=msg["content"]
        ))

    # 解析工具
    tools = None
    if "tools" in data:
        tools = []
        for tool in data["tools"]:
            tools.append(ClaudeTool(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["input_schema"]
            ))

    return ClaudeRequest(
        model=data.get("model", "claude-sonnet-4.5"),
        messages=messages,
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature"),
        tools=tools,
        stream=data.get("stream", True),
        system=data.get("system")
    )


if __name__ == "__main__":
    import uvicorn

    # 读取配置
    try:
        import asyncio
        config = asyncio.run(read_global_config())
        port = config.port
    except Exception as e:
        logger.error(f"无法读取配置: {e}")
        port = 8080

    logger.info(f"正在启动服务，监听端口 {port}...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
