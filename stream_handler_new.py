"""
SSE 流处理模块（更新版）
处理 Amazon Q Event Stream 响应并转换为 Claude 格式
"""
import logging
from typing import AsyncIterator, Optional
from event_stream_parser import EventStreamParser, extract_event_info
from parser import (
    parse_amazonq_event,
    build_claude_ping_event,
    build_claude_message_start_event,
    build_claude_content_block_start_event,
    build_claude_content_block_delta_event,
    build_claude_content_block_stop_event,
    build_claude_message_stop_event,
    build_claude_tool_use_start_event,
    build_claude_tool_use_input_delta_event
)
from models import (
    MessageStart,
    ContentBlockDelta,
    ContentBlockStop,
    MessageStop,
    AssistantResponseEnd
)

logger = logging.getLogger(__name__)


class AmazonQStreamHandler:
    """Amazon Q Event Stream 处理器"""

    def __init__(self, model: str = "claude-3.5-sonnet", request_data: Optional[dict] = None):
        # 响应文本累积缓冲区
        self.response_buffer: list[str] = []

        # 内容块索引
        self.content_block_index: int = -1

        # 内容块是否已开始
        self.content_block_started: bool = False

        # 内容块开始是否已发送
        self.content_block_start_sent: bool = False

        # 内容块停止是否已发送
        self.content_block_stop_sent: bool = False

        # 对话 ID
        self.conversation_id: Optional[str] = None

        # 原始请求的 model
        self.model: str = model

        # 输入 token 数量(小模型返回0避免累积)
        is_small_model = self._is_small_model_request(request_data)
        if is_small_model:
            logger.info(f"检测到小模型请求,input_tokens 设置为 0")
            self.input_tokens = 0
        elif request_data:
            self.input_tokens = self._estimate_input_tokens(request_data)
        else:
            logger.warning("request_data 为 None,input_tokens 设置为 0")
            self.input_tokens = 0

        # 是否已发送 message_start
        self.message_start_sent: bool = False

        # Tool use 相关状态
        self.current_tool_use: Optional[dict] = None  # 当前正在处理的工具调用
        self.tool_input_buffer: list[str] = []  # 累积 tool input 片段
        self.tool_use_id: Optional[str] = None  # 当前 tool use ID
        self.tool_name: Optional[str] = None  # 当前 tool name

        # 已处理的 tool_use_id 集合（用于去重）
        self._processed_tool_use_ids: set = set()
        
        # 所有 tool use 的完整 input(用于 token 统计)
        self.all_tool_inputs: list[str] = []

    async def handle_stream(
        self,
        upstream_bytes: AsyncIterator[bytes]
    ) -> AsyncIterator[str]:
        """
        处理上游 Event Stream 并转换为 Claude 格式

        Args:
            upstream_bytes: 上游字节流（Amazon Q Event Stream）

        Yields:
            str: Claude 格式的 SSE 事件
        """
        try:
            # 使用 Event Stream 解析器
            parser = EventStreamParser()

            async for message in parser.parse_stream(upstream_bytes):
                # 提取事件信息
                event_info = extract_event_info(message)
                if not event_info:
                    continue

                # 记录收到的事件类型
                event_type = event_info.get('event_type')
                logger.info(f"收到 Amazon Q 事件: {event_type}")

                # 记录完整的事件信息（调试级别）
                import json
                logger.debug(f"事件详情: {json.dumps(event_info, ensure_ascii=False, indent=2)}")

                # 解析为标准事件对象
                event = parse_amazonq_event(event_info)
                if not event:
                    # 检查是否是 toolUseEvent 的原始 payload
                    if event_type == 'toolUseEvent':
                        logger.info(f"处理 toolUseEvent: {event_info.get('payload', {})}")
                        # 直接处理 tool use 事件
                        async for cli_event in self._handle_tool_use_event(event_info.get('payload', {})):
                            yield cli_event
                    else:
                        logger.warning(f"跳过未知事件类型: {event_type}")
                    continue

                # 根据事件类型处理
                if isinstance(event, MessageStart):
                    # 处理 initial-response 事件
                    if event.message:
                        self.conversation_id = event.message.conversationId

                    # 发送 message_start
                    if not self.message_start_sent:
                        cli_event = build_claude_message_start_event(
                            self.conversation_id or "unknown",
                            self.model
                        )
                        yield cli_event
                        self.message_start_sent = True

                        # 在 message_start 之后发送 ping
                        yield build_claude_ping_event()

                elif isinstance(event, ContentBlockDelta):
                    # 处理 assistantResponseEvent 事件

                    # 如果之前有 tool use 块未关闭,先关闭它
                    if self.current_tool_use and not self.content_block_stop_sent:
                        cli_event = build_claude_content_block_stop_event(self.content_block_index)
                        logger.debug(f"关闭 tool use 块: index={self.content_block_index}")
                        yield cli_event
                        self.content_block_stop_sent = True
                        self.current_tool_use = None

                    # 首次收到内容时，发送 content_block_start
                    if not self.content_block_start_sent:
                        # 内容块索引递增
                        self.content_block_index += 1
                        cli_event = build_claude_content_block_start_event(
                            self.content_block_index
                        )
                        yield cli_event
                        self.content_block_start_sent = True
                        self.content_block_started = True

                    # 发送内容增量
                    if event.delta and event.delta.text:
                        text_chunk = event.delta.text

                        # 追加到缓冲区
                        self.response_buffer.append(text_chunk)

                        # 构建并发送事件
                        cli_event = build_claude_content_block_delta_event(
                            self.content_block_index,
                            text_chunk
                        )
                        yield cli_event

                elif isinstance(event, AssistantResponseEnd):
                    # 处理助手响应结束事件
                    logger.info(f"收到助手响应结束事件，toolUses数量: {len(event.tool_uses)}")

                    # Note: toolUses 已经在 toolUseEvent 中处理，这里不需要重复处理
                    # 检查是否需要发送 content_block_stop
                    if self.content_block_started and not self.content_block_stop_sent:
                        cli_event = build_claude_content_block_stop_event(
                            self.content_block_index
                        )
                        yield cli_event
                        self.content_block_stop_sent = True

            # 流结束，发送收尾事件
            # 只有当 content_block_started 且尚未发送 content_block_stop 时才发送
            if self.content_block_started and not self.content_block_stop_sent:
                cli_event = build_claude_content_block_stop_event(
                    self.content_block_index
                )
                yield cli_event
                self.content_block_stop_sent = True

            # 计算 output token 数量：文本响应 + 所有 tool use inputs
            full_text_response = "".join(self.response_buffer)
            full_tool_inputs = "".join(self.all_tool_inputs)
            output_tokens = self._count_tokens(full_text_response + full_tool_inputs)
            
            logger.info(f"Token 统计 - 输入: {self.input_tokens}, 输出: {output_tokens} (文本: {len(full_text_response)} 字符, tool inputs: {len(full_tool_inputs)} 字符)")

            cli_event = build_claude_message_stop_event(
                self.input_tokens,
                output_tokens,
                "end_turn"
            )
            yield cli_event

        except Exception as e:
            logger.error(f"处理流时发生错误: {e}", exc_info=True)
            raise

    async def _handle_tool_use_event(self, payload: dict) -> AsyncIterator[str]:
        """
        处理 tool use 事件

        Args:
            payload: tool use 事件的 payload

        Yields:
            str: Claude 格式的 tool use 事件
        """
        try:
            # 提取 tool use 信息
            tool_use_id = payload.get('toolUseId')
            tool_name = payload.get('name')
            tool_input = payload.get('input', {})
            is_stop = payload.get('stop', False)

            logger.info(f"Tool use 事件 - ID: {tool_use_id}, Name: {tool_name}, Stop: {is_stop}")
            logger.debug(f"Tool input: {tool_input}")

            # 添加去重机制：检查是否已经处理过这个 tool_use_id
            # if tool_use_id and not is_stop:
                # 如果这个 tool_use_id 已经在当前工具调用中，说明是重复事件
                # if self.tool_use_id == tool_use_id and self.current_tool_use:
                #     logger.warning(f"检测到重复的 tool use 事件，toolUseId={tool_use_id}，跳过处理")
                #     return
                # # 如果这个 tool_use_id 之前处理过但已经完成，也是重复事件
                # elif tool_use_id in self._processed_tool_use_ids:
                #     logger.warning(f"检测到已处理过的 tool use 事件，toolUseId={tool_use_id}，跳过处理")
                #     return

            # 如果是新 tool use 事件的开始
            if tool_use_id and tool_name and not self.current_tool_use:
                logger.info(f"开始新的 tool use: {tool_name} (ID: {tool_use_id})")

                # 如果之前有文本块未关闭,先关闭它
                if self.content_block_start_sent and not self.content_block_stop_sent:
                    cli_event = build_claude_content_block_stop_event(self.content_block_index)
                    logger.debug(f"关闭文本块: index={self.content_block_index}")
                    yield cli_event
                    self.content_block_stop_sent = True

                # 记录这个 tool_use_id 为已处理
                self._processed_tool_use_ids.add(tool_use_id)

                # 内容块索引递增
                self.content_block_index += 1

                # 发送 content_block_start (tool_use type)
                cli_event = build_claude_tool_use_start_event(
                    self.content_block_index,
                    tool_use_id,
                    tool_name
                )
                logger.debug(f"发送 content_block_start (tool_use): index={self.content_block_index}")
                yield cli_event

                self.content_block_started = True
                self.current_tool_use = {
                    'toolUseId': tool_use_id,
                    'name': tool_name
                }
                self.tool_use_id = tool_use_id
                self.tool_name = tool_name
                self.tool_input_buffer = []  # 用于累积字符串片段

            # 如果是正在处理的 tool use，累积 input 片段
            if self.current_tool_use and tool_input:
                # Amazon Q 的 input 是字符串片段，需要累积
                # 注意：tool_input 可能是字符串或字典
                if isinstance(tool_input, str):
                    # 字符串片段，直接累积
                    input_fragment = tool_input
                    self.tool_input_buffer.append(input_fragment)
                    logger.debug(f"累积 input 片段: '{input_fragment}' (总长度: {sum(len(s) for s in self.tool_input_buffer)})")
                elif isinstance(tool_input, dict):
                    # 如果是字典，转换为 JSON 字符串
                    import json
                    input_fragment = json.dumps(tool_input, ensure_ascii=False)
                    self.tool_input_buffer.append(input_fragment)
                    logger.debug(f"累积 input 对象: {len(input_fragment)} 字符")
                else:
                    logger.warning(f"未知的 input 类型: {type(tool_input)}")
                    input_fragment = str(tool_input)
                    self.tool_input_buffer.append(input_fragment)

                # 发送 input_json_delta（发送原始片段）
                cli_event = build_claude_tool_use_input_delta_event(
                    self.content_block_index,
                    input_fragment
                )
                yield cli_event

            # 如果是 stop 事件，发送 content_block_stop
            if is_stop and self.current_tool_use:
                # 记录完整的累积 input
                full_input = "".join(self.tool_input_buffer)
                logger.info(f"完成 tool use: {self.tool_name} (ID: {self.tool_use_id})")
                logger.info(f"完整 input ({len(full_input)} 字符): {full_input}")
                
                # 保存完整的 tool input 用于 token 统计
                self.all_tool_inputs.append(full_input)

                cli_event = build_claude_content_block_stop_event(
                    self.content_block_index
                )
                logger.debug(f"发送 content_block_stop: index={self.content_block_index}")
                yield cli_event

                # 标记 content_block_stop 已发送，避免重复发送
                self.content_block_stop_sent = True
                # 重置 content_started 状态
                self.content_block_started = False

                # 清理状态
                self.current_tool_use = None
                self.tool_use_id = None
                self.tool_name = None
                self.tool_input_buffer = []

        except Exception as e:
            logger.error(f"处理 tool use 事件失败: {e}", exc_info=True)
            raise

    def _is_small_model_request(self, request_data: Optional[dict]) -> bool:
        """
        判断是否是小模型请求(返回 input_tokens=0)

        Args:
            request_data: Claude API 请求数据

        Returns:
            bool: 是否是小模型请求
        """
        if not request_data:
            return False

        model = request_data.get('model', '').lower()

        # 从配置读取小模型列表
        from config import get_config_sync
        try:
            config = get_config_sync()
            zero_token_models = config.zero_input_token_models
        except:
            zero_token_models = ['haiku']

        # 使用更严格的匹配:关键词必须作为独立单词出现(用 - 或 _ 分隔)
        import re
        for keyword in zero_token_models:
            # 转义特殊字符,构建单词边界匹配模式
            pattern = r'(^|[-_])' + re.escape(keyword) + r'([-_]|$)'
            if re.search(pattern, model):
                return True
        return False

    def _count_tokens(self, text: str) -> int:
        """
        计算文本的 token 数量
        使用 tiktoken 精确计算,失败时回退到简化估算

        Args:
            text: 文本内容

        Returns:
            int: token 数量
        """
        if not text:
            return 0
        
        try:
            import tiktoken
            # Claude 使用类似 GPT-4 的 tokenizer (cl100k_base)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            # 回退到简化估算:平均每 4 个字符约等于 1 个 token
            logger.debug(f"tiktoken 计数失败,使用简化估算: {e}")
            return max(1, len(text) // 4)
    
    def _estimate_input_tokens(self, request_data: dict) -> int:
        """
        估算输入 token 数量

        Args:
            request_data: Claude API 请求数据

        Returns:
            int: 估算的输入 token 数量
        """
        try:
            import json

            # 收集所有文本内容
            text_parts = []

            # 统计 system prompt (可能是字符串或数组)
            system = request_data.get('system', '')
            if system:
                if isinstance(system, str):
                    text_parts.append(system)
                elif isinstance(system, list):
                    # 提取所有文本块的内容
                    for block in system:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            text_parts.append(block.get('text', ''))

            # 统计所有消息内容
            messages = request_data.get('messages', [])
            for msg in messages:
                content = msg.get('content', '')
                if isinstance(content, str):
                    text_parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get('type') == 'text':
                                text_parts.append(block.get('text', ''))
                            elif block.get('type') == 'tool_use':
                                text_parts.append(block.get('name', ''))
                                text_parts.append(json.dumps(block.get('input', {})))
                            elif block.get('type') == 'tool_result':
                                tool_result_content = block.get('content', [])
                                if isinstance(tool_result_content, str):
                                    text_parts.append(tool_result_content)
                                elif isinstance(tool_result_content, list):
                                    for result_block in tool_result_content:
                                        if isinstance(result_block, dict) and result_block.get('type') == 'text':
                                            text_parts.append(result_block.get('text', ''))
                                        elif isinstance(result_block, str):
                                            text_parts.append(result_block)

            # 统计 tools 定义
            tools = request_data.get('tools', [])
            for tool in tools:
                text_parts.append(tool.get('name', ''))
                text_parts.append(tool.get('description', ''))
                text_parts.append(json.dumps(tool.get('input_schema', {})))

            # 使用 tiktoken 精确计算
            full_text = '\n'.join(text_parts)
            estimated_tokens = self._count_tokens(full_text)

            logger.info(f"估算输入 tokens: {estimated_tokens}")
            return estimated_tokens

        except Exception as e:
            logger.warning(f"估算输入 token 失败: {e}")
            return 0


async def handle_amazonq_stream(
    upstream_bytes: AsyncIterator[bytes],
    model: str = "claude-3.5-sonnet",
    request_data: Optional[dict] = None
) -> AsyncIterator[str]:
    """
    处理 Amazon Q Event Stream 的便捷函数

    Args:
        upstream_bytes: 上游字节流
        model: 原始请求的 model 名称
        request_data: 原始 Claude API 请求数据(用于估算 input tokens)

    Yields:
        str: Claude 格式的 SSE 事件
    """
    handler = AmazonQStreamHandler(model=model, request_data=request_data)
    async for event in handler.handle_stream(upstream_bytes):
        yield event
