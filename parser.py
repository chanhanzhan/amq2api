"""
事件解析模块
解析 Amazon Q / CodeWhisperer 事件数据
支持 AWS Event Stream 格式
"""
import json
import logging
from typing import Optional, Dict, Any
from models import (
    CodeWhispererEventData,
    MessageStart,
    ContentBlockStart,
    ContentBlockDelta,
    ContentBlockStop,
    MessageStop,
    CodeWhispererToolUse,
    Message,
    ContentBlock,
    Delta,
    Usage,
    AssistantResponseEnd
)

logger = logging.getLogger(__name__)


def parse_event_data(json_string: str) -> Optional[CodeWhispererEventData]:
    """
    解析 CodeWhisperer 事件数据

    Args:
        json_string: JSON 字符串

    Returns:
        Optional[CodeWhispererEventData]: 解析成功返回事件对象，失败返回 None
    """
    try:
        # 步骤 1: 解析 JSON
        json_object = json.loads(json_string)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return None

    # 检查是否是字典
    if not isinstance(json_object, dict):
        logger.error("JSON 对象不是字典类型")
        return None

    # 步骤 2: 根据字段匹配不同的事件类型
    try:
        # --- 尝试匹配标准事件（有 "type" 字段）---
        if "type" in json_object:
            event_type = json_object["type"]

            # message_start 事件
            if event_type == "message_start":
                message_data = json_object.get("message", {})
                conversation_id = message_data.get("id") or message_data.get("conversationId")

                if conversation_id:
                    message = Message(
                        conversationId=conversation_id,
                        role=message_data.get("role", "assistant")
                    )
                    return MessageStart(message=message)

            # content_block_start 事件
            elif event_type == "content_block_start":
                if "content_block" in json_object and "index" in json_object:
                    index = json_object["index"]
                    content_type = json_object["content_block"].get("type", "text")

                    content_block = ContentBlock(type=content_type)
                    return ContentBlockStart(index=index, content_block=content_block)

            # content_block_delta 事件
            elif event_type == "content_block_delta":
                if "delta" in json_object and "index" in json_object:
                    delta_data = json_object["delta"]
                    text_chunk = delta_data.get("text")
                    index = json_object["index"]

                    if text_chunk is not None:
                        delta = Delta(
                            type=delta_data.get("type", "text_delta"),
                            text=text_chunk
                        )
                        return ContentBlockDelta(index=index, delta=delta)

            # content_block_stop 事件
            elif event_type == "content_block_stop":
                if "index" in json_object:
                    index = json_object["index"]
                    return ContentBlockStop(index=index)

            # message_stop 事件
            elif event_type == "message_stop":
                stop_reason = json_object.get("stop_reason")
                usage_data = json_object.get("usage")

                usage = None
                if usage_data:
                    usage = Usage(
                        input_tokens=usage_data.get("input_tokens", 0),
                        output_tokens=usage_data.get("output_tokens", 0)
                    )

                return MessageStop(stop_reason=stop_reason, usage=usage)

        # --- 尝试匹配 ToolUse 事件（没有 "type" 字段）---
        if "toolUseId" in json_object and "name" in json_object and "input" in json_object:
            tool_use_id = json_object["toolUseId"]
            name = json_object["name"]
            input_data = json_object["input"]

            return CodeWhispererToolUse(
                toolUseId=tool_use_id,
                name=name,
                input=input_data
            )

        # 如果所有模式都不匹配
        logger.warning(f"未知的事件类型: {json_object}")
        return None

    except Exception as e:
        logger.error(f"解析事件数据时发生错误: {e}")
        return None


def parse_sse_line(line: str) -> Optional[str]:
    """
    解析 SSE 行，提取 data 字段

    Args:
        line: SSE 行（例如 "data: {...}"）

    Returns:
        Optional[str]: 提取的 JSON 字符串，如果不是 data 行则返回 None
    """
    line = line.strip()

    # 跳过空行和注释
    if not line or line.startswith(":"):
        return None

    # 解析 data: 行
    if line.startswith("data:"):
        data = line[5:].strip()  # 移除 "data:" 前缀
        return data

    return None


def build_claude_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """
    构建 Claude SSE 格式的事件

    Args:
        event_type: 事件类型
        data: 事件数据

    Returns:
        str: SSE 格式的事件字符串
    """
    json_data = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {json_data}\n\n"


def build_claude_message_start_event(conversation_id: str, model: str = "claude-3.5-sonnet") -> str:
    """构建 message_start 事件"""
    data = {
        "type": "message_start",
        "message": {
            "id": conversation_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}
        }
    }
    return build_claude_sse_event("message_start", data)


def build_claude_content_block_start_event(index: int) -> str:
    """构建 content_block_start 事件"""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": "text", "text": ""}
    }
    return build_claude_sse_event("content_block_start", data)


def build_claude_content_block_delta_event(index: int, text: str) -> str:
    """构建 content_block_delta 事件"""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "text_delta", "text": text}
    }
    return build_claude_sse_event("content_block_delta", data)


def build_claude_content_block_stop_event(index: int) -> str:
    """构建 content_block_stop 事件"""
    data = {
        "type": "content_block_stop",
        "index": index
    }
    return build_claude_sse_event("content_block_stop", data)


def build_claude_ping_event() -> str:
    """构建 ping 事件(保持连接活跃)"""
    data = {"type": "ping"}
    return build_claude_sse_event("ping", data)


def build_claude_message_stop_event(
    input_tokens: int,
    output_tokens: int,
    stop_reason: Optional[str] = None
) -> str:
    """构建 message_delta 和 message_stop 事件"""
    # 先发送 message_delta
    delta_data = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason or "end_turn", "stop_sequence": None},
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}
    }
    delta_event = build_claude_sse_event("message_delta", delta_data)

    # 再发送 message_stop（包含最终 usage）
    stop_data = {
        "type": "message_stop",
        "stop_reason": stop_reason or "end_turn",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}
    }
    stop_event = build_claude_sse_event("message_stop", stop_data)

    return delta_event + stop_event


def build_claude_tool_use_start_event(index: int, tool_use_id: str, tool_name: str) -> str:
    """构建 tool use 类型的 content_block_start 事件"""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {
            "type": "tool_use",
            "id": tool_use_id,
            "name": tool_name
        }
    }
    return build_claude_sse_event("content_block_start", data)


def build_claude_tool_use_input_delta_event(index: int, input_json_delta: str) -> str:
    """构建 tool use input 内容的 content_block_delta 事件"""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {
            "type": "input_json_delta",
            "partial_json": input_json_delta
        }
    }
    return build_claude_sse_event("content_block_delta", data)


# ============================================================================
# Amazon Q Event Stream 特定解析函数
# ============================================================================

def parse_amazonq_event(event_info: Dict[str, Any]) -> Optional[CodeWhispererEventData]:
    """
    解析 Amazon Q Event Stream 事件

    Amazon Q 事件格式：
    - event_type: "initial-response" | "assistantResponseEvent" | "toolUseEvent"
    - payload: {"conversationId": "..."} | {"content": "..."} | {"name": "...", "toolUseId": "...", "input": "...", "stop": true/false}

    Args:
        event_info: 从 Event Stream 提取的事件信息

    Returns:
        Optional[CodeWhispererEventData]: 转换后的事件对象
    """
    event_type = event_info.get('event_type')
    payload = event_info.get('payload')

    if not event_type or not payload:
        return None

    try:
        # initial-response 事件 -> MessageStart
        if event_type == 'initial-response':
            conversation_id = payload.get('conversationId', '')
            import uuid
            message = Message(
                conversationId=conversation_id or str(uuid.uuid4()),
                role="assistant"
            )
            return MessageStart(message=message)

        # assistantResponseEvent 事件 -> ContentBlockDelta
        elif event_type == 'assistantResponseEvent':
            content = payload.get('content', '')
            tool_uses = payload.get('toolUses', [])

            # 如果有文本内容，返回文本增量事件
            if content:
                delta = Delta(
                    type="text_delta",
                    text=content
                )
                # Amazon Q 不提供 index，默认使用 0
                return ContentBlockDelta(index=0, delta=delta)

            # 如果有 toolUses，返回助手响应事件（用于构建完整的助手消息）
            if tool_uses:
                # 这表示助手响应的结束，包含 toolUses
                return AssistantResponseEnd(
                    tool_uses=tool_uses,
                    message_id=payload.get('messageId', '')
                )

        # toolUseEvent 事件 -> 需要特殊处理
        elif event_type == 'toolUseEvent':
            # 这是工具调用事件，需要累积 input 片段
            # 返回 None，让 stream_handler 通过 event_type 检测并处理
            return None

        return None

    except Exception as e:
        logger.error(f"解析 Amazon Q 事件失败: {e}")
        return None