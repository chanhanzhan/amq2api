"""
OpenAI API format converter
Converts OpenAI chat completion format to Claude format
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def convert_openai_to_claude(openai_request: dict) -> dict:
    """
    Convert OpenAI API request format to Claude API format
    
    OpenAI format:
    {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "https://..."}}
            ]},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
        "stream": true,
        "tools": [...],
        "tool_choice": "auto"
    }
    
    Claude format:
    {
        "model": "claude-sonnet-4.5",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image", "source": {"type": "url", "url": "https://..."}}
            ]},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ],
        "system": "You are a helpful assistant",
        "temperature": 0.7,
        "max_tokens": 1000,
        "stream": true,
        "tools": [...]
    }
    """
    claude_request = {}
    
    # Convert model name
    openai_model = openai_request.get("model", "gpt-4")
    claude_request["model"] = convert_openai_model_to_claude(openai_model)
    
    # Extract system message and convert messages
    messages = openai_request.get("messages", [])
    system_message = None
    claude_messages = []
    
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        
        if role == "system":
            # Claude uses a separate system parameter
            system_message = content
        elif role in ["user", "assistant"]:
            # Handle multimodal content
            converted_content = convert_openai_content_to_claude(content)
            claude_messages.append({
                "role": role,
                "content": converted_content
            })
        elif role == "tool":
            # OpenAI tool response format
            tool_call_id = msg.get("tool_call_id")
            claude_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": content
                    }
                ]
            })
    
    claude_request["messages"] = claude_messages
    
    if system_message:
        claude_request["system"] = system_message
    
    # Copy other parameters
    if "temperature" in openai_request:
        claude_request["temperature"] = openai_request["temperature"]
    
    if "max_tokens" in openai_request:
        claude_request["max_tokens"] = openai_request["max_tokens"]
    else:
        claude_request["max_tokens"] = 4096  # Default
    
    if "stream" in openai_request:
        claude_request["stream"] = openai_request["stream"]
    else:
        claude_request["stream"] = False  # Default to non-streaming (OpenAI API standard)
    
    # Convert tools if present
    if "tools" in openai_request:
        claude_tools = []
        for tool in openai_request["tools"]:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                claude_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {})
                })
        if claude_tools:
            claude_request["tools"] = claude_tools
    
    # Note: tool_choice is handled differently in Claude
    # OpenAI: "auto", "none", or specific function
    # Claude: doesn't have direct equivalent, will use default behavior
    
    logger.info(f"Converted OpenAI request (model: {openai_model}) to Claude format")
    return claude_request


def convert_openai_content_to_claude(content):
    """
    Convert OpenAI message content to Claude format
    
    OpenAI supports:
    - String: "Hello"
    - Array: [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}}]
    
    Claude supports:
    - String: "Hello"
    - Array: [{"type": "text", "text": "..."}, {"type": "image", "source": {...}}]
    """
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        claude_content = []
        for item in content:
            item_type = item.get("type")
            
            if item_type == "text":
                # Text content remains the same
                claude_content.append({
                    "type": "text",
                    "text": item.get("text", "")
                })
            
            elif item_type == "image_url":
                # Convert OpenAI image_url format to Claude image format
                image_url = item.get("image_url", {})
                url = image_url.get("url", "")
                
                # Check if it's a base64 image or URL
                if url.startswith("data:"):
                    # Base64 image: data:image/jpeg;base64,<data>
                    import re
                    # Use non-greedy match and specific character classes to prevent ReDoS
                    match = re.match(r'data:(image/[a-zA-Z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$', url)
                    if match:
                        media_type = match.group(1)
                        base64_data = match.group(2)
                        claude_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_data
                            }
                        })
                else:
                    # URL image
                    claude_content.append({
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": url
                        }
                    })
        
        return claude_content if claude_content else content
    
    return content


def convert_openai_model_to_claude(openai_model: str) -> str:
    """
    Convert OpenAI model name to Claude model name
    现在直接返回原始模型名称，不进行映射
    """
    # 直接返回原始模型名称，不进行映射
    return openai_model


def convert_claude_to_openai_stream(claude_event: dict, event_type: str) -> Optional[str]:
    """
    Convert Claude SSE event to OpenAI stream format
    
    Claude events: message_start, content_block_start, content_block_delta, content_block_stop, message_delta, message_stop
    OpenAI format: data: {"id":"...", "object":"chat.completion.chunk", "choices":[{"delta":{"content":"..."}}]}
    """
    import json
    import uuid
    
    if event_type == "message_start":
        # Send initial chunk with role
        openai_chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "created": int(claude_event.get("created", 0)),
            "model": claude_event.get("model", "gpt-4"),
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "content": ""
                },
                "finish_reason": None
            }]
        }
        return f"data: {json.dumps(openai_chunk)}\n\n"
    
    elif event_type == "content_block_delta":
        # Extract text from delta
        delta = claude_event.get("delta", {})
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            openai_chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion.chunk",
                "created": int(claude_event.get("created", 0)),
                "model": claude_event.get("model", "gpt-4"),
                "choices": [{
                    "index": 0,
                    "delta": {
                        "content": text
                    },
                    "finish_reason": None
                }]
            }
            return f"data: {json.dumps(openai_chunk)}\n\n"
        elif delta.get("type") == "input_json_delta":
            # Tool use input delta - accumulate but don't send yet
            # Will be sent in content_block_stop
            return None
    
    elif event_type == "content_block_start":
        # Check if it's a tool use block
        content_block = claude_event.get("content_block", {})
        if content_block.get("type") == "tool_use":
            # Start of tool call
            tool_use_id = content_block.get("id")
            tool_name = content_block.get("name")
            
            openai_chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion.chunk",
                "created": int(claude_event.get("created", 0)),
                "model": claude_event.get("model", "gpt-4"),
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": claude_event.get("index", 0),
                            "id": tool_use_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": ""
                            }
                        }]
                    },
                    "finish_reason": None
                }]
            }
            return f"data: {json.dumps(openai_chunk)}\n\n"
    
    elif event_type == "content_block_stop":
        # Check if it contains tool use information
        content_block = claude_event.get("content_block", {})
        if content_block and content_block.get("type") == "tool_use":
            # Send complete tool call
            tool_use_id = content_block.get("id")
            tool_name = content_block.get("name")
            tool_input = content_block.get("input", {})
            
            openai_chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion.chunk",
                "created": int(claude_event.get("created", 0)),
                "model": claude_event.get("model", "gpt-4"),
                "choices": [{
                    "index": 0,
                    "delta": {
                        "tool_calls": [{
                            "index": claude_event.get("index", 0),
                            "id": tool_use_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_input)
                            }
                        }]
                    },
                    "finish_reason": None
                }]
            }
            return f"data: {json.dumps(openai_chunk)}\n\n"
    
    elif event_type == "message_stop":
        # Send final chunk with finish_reason
        stop_reason = claude_event.get("stop_reason", "stop")
        
        # Map Claude stop reasons to OpenAI format
        finish_reason_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "tool_use": "tool_calls"
        }
        finish_reason = finish_reason_map.get(stop_reason, "stop")
        
        openai_chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "created": int(claude_event.get("created", 0)),
            "model": claude_event.get("model", "gpt-4"),
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason
            }]
        }
        return f"data: {json.dumps(openai_chunk)}\n\ndata: [DONE]\n\n"
    
    return None


def convert_claude_to_openai_non_stream(claude_events: list[dict]) -> dict:
    """
    Convert Claude SSE events to OpenAI non-stream format
    
    Args:
        claude_events: List of Claude event dictionaries
        
    Returns:
        OpenAI format response dictionary
    """
    import json
    import uuid
    from datetime import datetime
    
    # Accumulate content and tool calls
    content_parts = []
    tool_calls = []
    finish_reason = "stop"
    model = "gpt-4"
    created = int(datetime.now().timestamp())
    response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    
    # Process events
    for event in claude_events:
        event_type = event.get("type")
        
        if event_type == "message_start":
            # Extract model from message object if available
            message = event.get("message", {})
            if message:
                model = message.get("model", event.get("model", "gpt-4"))
            else:
                model = event.get("model", "gpt-4")
            created = event.get("created", created)
        
        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:  # Only append non-empty text
                    content_parts.append(text)
        
        elif event_type == "content_block_start":
            content_block = event.get("content_block", {})
            if content_block.get("type") == "tool_use":
                tool_use_id = content_block.get("id")
                tool_name = content_block.get("name")
                tool_calls.append({
                    "id": tool_use_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": ""
                    }
                })
        
        elif event_type == "content_block_stop":
            content_block = event.get("content_block", {})
            if content_block and content_block.get("type") == "tool_use":
                tool_use_id = content_block.get("id")
                tool_input = content_block.get("input", {})
                # Find and update the tool call
                for tool_call in tool_calls:
                    if tool_call["id"] == tool_use_id:
                        tool_call["function"]["arguments"] = json.dumps(tool_input)
                        break
        
        elif event_type == "message_stop":
            stop_reason = event.get("stop_reason", "stop")
            finish_reason_map = {
                "end_turn": "stop",
                "max_tokens": "length",
                "stop_sequence": "stop",
                "tool_use": "tool_calls"
            }
            finish_reason = finish_reason_map.get(stop_reason, "stop")
    
    # Build response
    content = "".join(content_parts)
    
    # Debug logging
    logger.debug(f"convert_claude_to_openai_non_stream: content_parts count={len(content_parts)}, content length={len(content)}, tool_calls count={len(tool_calls)}")
    
    choice = {
        "index": 0,
        "message": {
            "role": "assistant",
            "content": content if content else None
        },
        "finish_reason": finish_reason
    }
    
    # Add tool calls if present
    if tool_calls:
        choice["message"]["tool_calls"] = tool_calls
        # OpenAI format: content is None when tool_calls exist, but only if there's no text content
        # If both text and tool_calls exist, keep the text content
        if not content:
            choice["message"]["content"] = None
    
    # Extract usage from message_stop event if available
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    }
    
    # Try to find usage info in the last message_stop event
    for event in reversed(claude_events):
        if event.get("type") == "message_stop":
            if "usage" in event:
                usage = {
                    "prompt_tokens": event["usage"].get("input_tokens", 0),
                    "completion_tokens": event["usage"].get("output_tokens", 0),
                    "total_tokens": event["usage"].get("input_tokens", 0) + event["usage"].get("output_tokens", 0)
                }
            break
    
    return {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [choice],
        "usage": usage
    }
