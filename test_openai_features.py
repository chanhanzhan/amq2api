"""
测试 OpenAI API 功能
包括 /v1/models 端点、多模态支持和工具调用响应
"""
import asyncio
import json
import sys


async def test_models_endpoint():
    """测试 /v1/models 端点"""
    print("测试 /v1/models 端点...")
    try:
        import httpx
        from app_new import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get("/v1/models")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["object"] == "list"
        assert "data" in data
        assert len(data["data"]) >= 3  # 至少有 3 个模型
        
        # 检查模型格式
        first_model = data["data"][0]
        assert "id" in first_model
        assert "object" in first_model
        assert first_model["object"] == "model"
        
        print(f"✓ /v1/models 端点测试通过")
        print(f"  - 返回 {len(data['data'])} 个模型")
        print(f"  - 模型列表: {[m['id'] for m in data['data'][:3]]}")
        return True
    except ImportError as e:
        print(f"⚠ 跳过测试 (缺少依赖): {e}")
        return True  # 跳过不算失败
    except Exception as e:
        print(f"✗ /v1/models 端点测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multimodal_conversion():
    """测试多模态内容转换"""
    print("\n测试多模态内容转换...")
    try:
        from app.core.openai_converter import convert_openai_content_to_claude
        
        # 测试文本内容
        text_content = "Hello, world!"
        result = convert_openai_content_to_claude(text_content)
        assert result == text_content
        print("✓ 文本内容转换正确")
        
        # 测试 base64 图片
        openai_image_base64 = [
            {"type": "text", "text": "What's in this image?"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
                }
            }
        ]
        
        result = convert_openai_content_to_claude(openai_image_base64)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image"
        assert result[1]["source"]["type"] == "base64"
        assert result[1]["source"]["media_type"] == "image/jpeg"
        print("✓ Base64 图片转换正确")
        
        # 测试 URL 图片
        openai_image_url = [
            {"type": "text", "text": "Describe this image"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://example.com/image.jpg"
                }
            }
        ]
        
        result = convert_openai_content_to_claude(openai_image_url)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[1]["type"] == "image"
        assert result[1]["source"]["type"] == "url"
        assert result[1]["source"]["url"] == "https://example.com/image.jpg"
        print("✓ URL 图片转换正确")
        
        return True
    except Exception as e:
        print(f"✗ 多模态转换测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_openai_to_claude_conversion():
    """测试 OpenAI 到 Claude 格式转换"""
    print("\n测试 OpenAI 到 Claude 格式转换...")
    try:
        from app.core.openai_converter import convert_openai_to_claude
        
        # 测试基本转换
        openai_request = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        claude_request = convert_openai_to_claude(openai_request)
        
        # 验证模型映射
        assert claude_request["model"] == "claude-sonnet-4"
        print("✓ 模型映射正确 (gpt-4 -> claude-sonnet-4)")
        
        # 验证系统消息提取
        assert claude_request["system"] == "You are a helpful assistant"
        print("✓ 系统消息提取正确")
        
        # 验证消息列表（不包含系统消息）
        assert len(claude_request["messages"]) == 3
        assert claude_request["messages"][0]["role"] == "user"
        assert claude_request["messages"][1]["role"] == "assistant"
        print("✓ 消息列表转换正确")
        
        # 验证其他参数
        assert claude_request["temperature"] == 0.7
        assert claude_request["max_tokens"] == 1000
        print("✓ 参数传递正确")
        
        # 测试工具转换
        openai_request_with_tools = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "What's the weather?"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"}
                            }
                        }
                    }
                }
            ]
        }
        
        claude_request = convert_openai_to_claude(openai_request_with_tools)
        
        assert "tools" in claude_request
        assert len(claude_request["tools"]) == 1
        assert claude_request["tools"][0]["name"] == "get_weather"
        assert claude_request["tools"][0]["description"] == "Get weather information"
        print("✓ 工具定义转换正确")
        
        return True
    except Exception as e:
        print(f"✗ OpenAI 转换测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_image_text_extraction():
    """测试图片内容提取"""
    print("\n测试图片内容提取...")
    try:
        from models import extract_text_from_claude_content
        
        # 测试包含图片的内容
        content_with_image = [
            {"type": "text", "text": "Here is an image:"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": "base64data"
                }
            },
            {"type": "text", "text": "What do you see?"}
        ]
        
        result = extract_text_from_claude_content(content_with_image)
        
        # 应该包含文本和图片占位符
        assert "Here is an image:" in result
        assert "[Image: image/jpeg]" in result
        assert "What do you see?" in result
        print("✓ 图片占位符提取正确")
        
        # 测试 URL 图片
        content_with_url_image = [
            {"type": "text", "text": "Check this:"},
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": "https://example.com/image.png"
                }
            }
        ]
        
        result = extract_text_from_claude_content(content_with_url_image)
        assert "[Image: https://example.com/image.png]" in result
        print("✓ URL 图片占位符提取正确")
        
        return True
    except Exception as e:
        print(f"✗ 图片文本提取测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_tool_call_stream_conversion():
    """测试工具调用流式响应转换"""
    print("\n测试工具调用流式响应转换...")
    try:
        from app.core.openai_converter import convert_claude_to_openai_stream
        
        # 测试 message_start 事件
        message_start = {
            "type": "message_start",
            "message": {"id": "msg_123", "role": "assistant"},
            "created": 1234567890,
            "model": "gpt-4"
        }
        
        result = convert_claude_to_openai_stream(message_start, "message_start")
        assert result is not None
        assert "data:" in result
        assert "role" in result
        assert "assistant" in result
        print("✓ message_start 事件转换正确")
        
        # 测试 content_block_start (tool_use)
        tool_start = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "tool_123",
                "name": "get_weather"
            },
            "created": 1234567890,
            "model": "gpt-4"
        }
        
        result = convert_claude_to_openai_stream(tool_start, "content_block_start")
        assert result is not None
        assert "tool_calls" in result
        assert "get_weather" in result
        print("✓ tool_use 开始事件转换正确")
        
        # 测试 content_block_stop (tool_use)
        tool_stop = {
            "type": "content_block_stop",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "tool_123",
                "name": "get_weather",
                "input": {"location": "San Francisco"}
            },
            "created": 1234567890,
            "model": "gpt-4"
        }
        
        result = convert_claude_to_openai_stream(tool_stop, "content_block_stop")
        assert result is not None
        assert "tool_calls" in result
        assert "San Francisco" in result
        print("✓ tool_use 完成事件转换正确")
        
        # 测试 message_stop
        message_stop = {
            "type": "message_stop",
            "stop_reason": "tool_use",
            "created": 1234567890,
            "model": "gpt-4"
        }
        
        result = convert_claude_to_openai_stream(message_stop, "message_stop")
        assert result is not None
        assert "tool_calls" in result  # finish_reason 应该是 tool_calls
        assert "[DONE]" in result
        print("✓ message_stop 事件转换正确")
        
        return True
    except Exception as e:
        print(f"✗ 工具调用流式转换测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("OpenAI API 功能测试")
    print("=" * 60)
    
    tests = [
        test_models_endpoint,
        test_multimodal_conversion,
        test_openai_to_claude_conversion,
        test_image_text_extraction,
        test_tool_call_stream_conversion
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"✗ 测试执行失败: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 60)
    print(f"测试完成: {sum(results)}/{len(results)} 通过")
    print("=" * 60)
    
    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
