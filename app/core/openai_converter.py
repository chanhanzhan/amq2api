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
            claude_messages.append({
                "role": role,
                "content": content
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
        claude_request["stream"] = True  # Default to streaming
    
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


def convert_openai_model_to_claude(openai_model: str) -> str:
    """
    Convert OpenAI model name to Claude model name
    """
    model_mapping = {
        "gpt-4": "claude-sonnet-4",
        "gpt-4-turbo": "claude-sonnet-4.5",
        "gpt-4-turbo-preview": "claude-sonnet-4.5",
        "gpt-4o": "claude-sonnet-4.5",
        "gpt-4o-mini": "claude-sonnet-4",
        "gpt-3.5-turbo": "claude-sonnet-4",
    }
    
    # Check for exact match
    if openai_model in model_mapping:
        return model_mapping[openai_model]
    
    # Default to claude-sonnet-4.5 for unknown models
    logger.info(f"Unknown OpenAI model {openai_model}, defaulting to claude-sonnet-4.5")
    return "claude-sonnet-4.5"


def convert_claude_to_openai_stream(claude_event: dict, event_type: str) -> Optional[str]:
    """
    Convert Claude SSE event to OpenAI stream format
    
    Claude events: message_start, content_block_start, content_block_delta, content_block_stop, message_delta, message_stop
    OpenAI format: data: {"id":"...", "object":"chat.completion.chunk", "choices":[{"delta":{"content":"..."}}]}
    """
    import json
    import uuid
    
    if event_type == "content_block_delta":
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
    
    elif event_type == "message_stop":
        # Send final chunk with finish_reason
        openai_chunk = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "created": int(claude_event.get("created", 0)),
            "model": claude_event.get("model", "gpt-4"),
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        return f"data: {json.dumps(openai_chunk)}\n\ndata: [DONE]\n\n"
    
    return None
