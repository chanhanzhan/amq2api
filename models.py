"""
数据结构定义
包含 Claude 和 CodeWhisperer 的请求/响应数据结构
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Literal
from enum import Enum


# ============================================================================
# Claude API 数据结构
# ============================================================================

@dataclass
class ClaudeTextContent:
    """Claude 文本内容块"""
    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ClaudeImageContent:
    """Claude 图片内容块"""
    type: Literal["image"] = "image"
    source: Dict[str, Any] = field(default_factory=dict)


ClaudeContent = Union[str, List[Union[ClaudeTextContent, ClaudeImageContent]]]


@dataclass
class ClaudeMessage:
    """Claude 消息"""
    role: Literal["user", "assistant"]
    content: ClaudeContent


@dataclass
class ClaudeTool:
    """Claude 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class ClaudeRequest:
    """Claude API 请求"""
    model: str
    messages: List[ClaudeMessage]
    max_tokens: int = 4096
    temperature: Optional[float] = None
    tools: Optional[List[ClaudeTool]] = None
    stream: bool = True
    system: Optional[Union[str, List[Dict[str, Any]]]] = None  # 可以是字符串或数组


# ============================================================================
# CodeWhisperer / Amazon Q 数据结构
# ============================================================================

@dataclass
class EnvState:
    """环境状态"""
    operatingSystem: str
    currentWorkingDirectory: str


@dataclass
class ToolSpecification:
    """工具规范"""
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class Tool:
    """工具定义"""
    toolSpecification: ToolSpecification


@dataclass
class UserInputMessageContext:
    """用户输入消息上下文"""
    envState: EnvState
    tools: List[Tool]
    toolResults: Optional[List[Dict[str, Any]]] = None  # 工具执行结果


@dataclass
class UserInputMessage:
    """用户输入消息"""
    content: str
    userInputMessageContext: UserInputMessageContext
    origin: str = "CLI"
    modelId: str = "claude-sonnet-4.5"


@dataclass
class CurrentMessage:
    """当前消息"""
    userInputMessage: UserInputMessage


@dataclass
class ConversationState:
    """对话状态"""
    conversationId: str
    history: List[Any]  # 历史消息列表
    currentMessage: CurrentMessage
    chatTriggerType: str = "MANUAL"


@dataclass
class CodeWhispererRequest:
    """CodeWhisperer API 请求"""
    conversationState: ConversationState
    profileArn: Optional[str] = None


# ============================================================================
# CodeWhisperer 事件数据结构
# ============================================================================

@dataclass
class Message:
    """消息对象"""
    conversationId: str
    role: str = "assistant"


@dataclass
class ContentBlock:
    """内容块"""
    type: str  # "text" or "code"


@dataclass
class Delta:
    """增量内容"""
    type: str  # "text_delta"
    text: str


@dataclass
class Usage:
    """使用统计"""
    input_tokens: int
    output_tokens: int


@dataclass
class MessageStart:
    """消息开始事件"""
    type: Literal["message_start"] = "message_start"
    message: Optional[Message] = None


@dataclass
class ContentBlockStart:
    """内容块开始事件"""
    type: Literal["content_block_start"] = "content_block_start"
    index: int = 0
    content_block: Optional[ContentBlock] = None


@dataclass
class ContentBlockDelta:
    """内容块增量事件"""
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int = 0
    delta: Optional[Delta] = None


@dataclass
class ContentBlockStop:
    """内容块停止事件"""
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int = 0


@dataclass
class MessageStop:
    """消息停止事件"""
    type: Literal["message_stop"] = "message_stop"
    stop_reason: Optional[str] = None
    usage: Optional[Usage] = None


@dataclass
class AssistantResponseEnd:
    """助手响应结束事件（包含 toolUses）"""
    type: Literal["assistant_response_end"] = "assistant_response_end"
    tool_uses: List[Dict[str, Any]] = field(default_factory=list)
    message_id: str = ""


@dataclass
class CodeWhispererToolUse:
    """工具使用事件"""
    toolUseId: str
    name: str
    input: Dict[str, Any]


# CodeWhisperer 事件数据的联合类型
CodeWhispererEventData = Union[
    MessageStart,
    ContentBlockStart,
    ContentBlockDelta,
    ContentBlockStop,
    MessageStop,
    AssistantResponseEnd,
    CodeWhispererToolUse
]


# ============================================================================
# 辅助函数
# ============================================================================

def claude_tool_to_codewhisperer_tool(claude_tool: ClaudeTool) -> Tool:
    """将 Claude 工具定义转换为 CodeWhisperer 工具定义"""
    # Amazon Q 的 description 字段有长度限制（10240 字符）
    # 如果超出，截断到 10200 字符并添加提示
    description = claude_tool.description
    if len(description) > 10240:
        description = description[:10100] + "\n\n...(Full description provided in TOOL DOCUMENTATION section)"

    # Amazon Q 需要 inputSchema 包装在 {"json": ...} 中
    spec = ToolSpecification(
        name=claude_tool.name,
        description=description,
        inputSchema={"json": claude_tool.input_schema}
    )
    return Tool(toolSpecification=spec)


def extract_text_from_claude_content(content: ClaudeContent) -> str:
    """从 Claude 内容中提取文本"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, ClaudeTextContent):
                text_parts.append(block.text)
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "image":
                    # 为图片添加占位符文本
                    source = block.get("source", {})
                    if source.get("type") == "base64":
                        media_type = source.get("media_type", "image")
                        text_parts.append(f"[Image: {media_type}]")
                    elif source.get("type") == "url":
                        url = source.get("url", "")
                        text_parts.append(f"[Image: {url}]")
        return "\n".join(text_parts)
    return ""