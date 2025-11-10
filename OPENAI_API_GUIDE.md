# OpenAI API 接口完整文档

本文档介绍 AMQ2API v2.0+ 中新增的 OpenAI API 兼容功能。

## 概述

AMQ2API 现在完全支持 OpenAI API 格式，包括：

- ✅ `/v1/models` 端点 - 列出可用模型
- ✅ `/v1/chat/completions` 端点 - 聊天完成（已存在）
- ✅ 多模态支持 - 图片输入（base64 和 URL）
- ✅ 工具调用 - 完整的 function calling 支持
- ✅ 系统提示词 - system message 支持

## 1. 模型列表端点

### GET /v1/models

列出所有可用的模型，兼容 OpenAI API 格式。

**请求示例：**

```bash
curl http://localhost:8080/v1/models
```

**响应示例：**

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-sonnet-4.5",
      "object": "model",
      "created": 1699564800,
      "owned_by": "anthropic",
      "permission": [],
      "root": "claude-sonnet-4.5",
      "parent": null
    },
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1699564800,
      "owned_by": "openai",
      "permission": [],
      "root": "gpt-4",
      "parent": null
    }
  ]
}
```

### 支持的模型

#### Claude 模型
- `claude-sonnet-4.5` - Claude 3.5 Sonnet (最新)
- `claude-sonnet-4` - Claude 3 Sonnet
- `claude-3-5-sonnet-20241022` - Claude 3.5 Sonnet (特定版本)

#### OpenAI 模型别名
这些模型会被映射到对应的 Claude 模型：

- `gpt-4` → `claude-sonnet-4`
- `gpt-4-turbo` → `claude-sonnet-4.5`
- `gpt-4o` → `claude-sonnet-4.5`
- `gpt-4o-mini` → `claude-sonnet-4`
- `gpt-3.5-turbo` → `claude-sonnet-4`

## 2. 多模态支持

### 图片输入

支持两种图片输入方式：

#### 方式 1：Base64 编码图片

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "这张图片里有什么？"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
            }
          }
        ]
      }
    ],
    "max_tokens": 1000
  }'
```

#### 方式 2：图片 URL

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {
        "role": "user",
        "content": [
          {
            "type": "text",
            "text": "描述这张图片"
          },
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/image.jpg"
            }
          }
        ]
      }
    ],
    "max_tokens": 1000
  }'
```

### 格式转换

系统会自动将 OpenAI 格式转换为 Claude 格式：

**OpenAI 格式：**
```json
{
  "type": "image_url",
  "image_url": {
    "url": "data:image/jpeg;base64,..."
  }
}
```

**转换为 Claude 格式：**
```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/jpeg",
    "data": "..."
  }
}
```

## 3. 系统提示词支持

### 使用方式

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {
        "role": "system",
        "content": "你是一个专业的 Python 编程助手，总是提供清晰、可运行的代码示例。"
      },
      {
        "role": "user",
        "content": "如何读取 CSV 文件？"
      }
    ],
    "max_tokens": 1000
  }'
```

### 转换说明

系统会自动提取 `system` 角色的消息，并转换为 Claude 的 `system` 参数：

**OpenAI 格式：**
```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "Hello"}
  ]
}
```

**转换为 Claude 格式：**
```json
{
  "system": "You are a helpful assistant",
  "messages": [
    {"role": "user", "content": "Hello"}
  ]
}
```

## 4. 工具调用（Function Calling）

### 定义工具

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {
        "role": "user",
        "content": "北京今天天气怎么样？"
      }
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "获取指定城市的天气信息",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {
                "type": "string",
                "description": "城市名称，例如：北京、上海"
              },
              "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "温度单位"
              }
            },
            "required": ["location"]
          }
        }
      }
    ],
    "max_tokens": 1000,
    "stream": true
  }'
```

### 流式响应格式

当模型决定调用工具时，会返回以下格式的流式响应：

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699564800,"model":"gpt-4","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699564800,"model":"gpt-4","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_abc123","type":"function","function":{"name":"get_weather","arguments":""}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699564800,"model":"gpt-4","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_abc123","type":"function","function":{"name":"get_weather","arguments":"{\"location\":\"北京\",\"unit\":\"celsius\"}"}}]},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1699564800,"model":"gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}

data: [DONE]
```

### 提交工具结果

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {
        "role": "user",
        "content": "北京今天天气怎么样？"
      },
      {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"location\":\"北京\",\"unit\":\"celsius\"}"
            }
          }
        ]
      },
      {
        "role": "tool",
        "tool_call_id": "call_abc123",
        "content": "{\"temperature\": 15, \"condition\": \"晴朗\", \"humidity\": 45}"
      }
    ],
    "tools": [...],
    "max_tokens": 1000
  }'
```

### 格式转换

**OpenAI 工具定义：**
```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "获取天气信息",
    "parameters": {...}
  }
}
```

**转换为 Claude 格式：**
```json
{
  "name": "get_weather",
  "description": "获取天气信息",
  "input_schema": {...}
}
```

## 5. 完整示例

### 多模态 + 工具调用示例

```python
import requests
import json
import base64

# 读取图片并转换为 base64
with open("image.jpg", "rb") as f:
    image_data = base64.b64encode(f.read()).decode()

# 发送请求
response = requests.post(
    "http://localhost:8080/v1/chat/completions",
    headers={
        "Authorization": "Bearer YOUR_API_KEY",
        "Content-Type": "application/json"
    },
    json={
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": "你是一个图像分析助手，可以识别图片中的物体并提供相关信息。"
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "这是什么植物？请告诉我它的学名和养护方法。"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}"
                        }
                    }
                ]
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_plant_info",
                    "description": "搜索植物的详细信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "plant_name": {
                                "type": "string",
                                "description": "植物的中文名或学名"
                            }
                        },
                        "required": ["plant_name"]
                    }
                }
            }
        ],
        "max_tokens": 2000,
        "stream": True
    },
    stream=True
)

# 处理流式响应
for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data: '):
            data_str = line_str[6:]
            if data_str != '[DONE]':
                data = json.loads(data_str)
                # 处理数据
                print(data)
```

## 6. 注意事项

### 1. API 密钥认证

所有请求都需要 API 密钥认证（v2.0+ 版本）：

```bash
# 使用 Authorization header
-H "Authorization: Bearer amq-your-api-key"

# 或使用 x-api-key header
-H "x-api-key: amq-your-api-key"
```

### 2. 图片大小限制

- Base64 编码图片建议不超过 20MB
- 图片会被转发到 Amazon Q，受其限制

### 3. 模型映射

- OpenAI 模型名会自动映射到 Claude 模型
- 建议直接使用 Claude 模型名以获得最佳体验

### 4. 流式响应

- 默认使用流式响应（`stream: true`）
- 非流式响应也支持，但流式体验更好

### 5. Token 计数

- 使用简化的 token 计数（约 4 字符 = 1 token）
- 实际 token 消耗可能有差异

## 7. 错误处理

### 常见错误码

- `400 Bad Request` - 请求格式错误
- `401 Unauthorized` - API 密钥无效或缺失
- `429 Too Many Requests` - 超过速率限制
- `500 Internal Server Error` - 服务器内部错误
- `502 Bad Gateway` - 上游 API 错误

### 错误响应格式

```json
{
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

## 8. 性能建议

1. **使用流式响应**
   - 降低首字节延迟
   - 提供更好的用户体验

2. **合理设置 max_tokens**
   - 避免不必要的长响应
   - 节省成本和时间

3. **批量处理**
   - 如果需要处理多个请求，考虑使用连接池
   - 复用 HTTP 连接

4. **缓存系统消息**
   - 相同的 system prompt 可以复用
   - 减少请求大小

## 9. 兼容性

### 与 OpenAI SDK 兼容

```python
from openai import OpenAI

# 配置客户端指向 AMQ2API
client = OpenAI(
    api_key="amq-your-api-key",
    base_url="http://localhost:8080/v1"
)

# 使用标准 OpenAI API
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ],
    stream=True
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

### 与 LangChain 兼容

```python
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

# 配置 LangChain
llm = ChatOpenAI(
    openai_api_key="amq-your-api-key",
    openai_api_base="http://localhost:8080/v1",
    model_name="gpt-4"
)

# 使用
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content="Hello!")
]

response = llm(messages)
print(response.content)
```

## 10. 更新日志

### v2.0.0 (2024-11)

- ✅ 新增 `/v1/models` 端点
- ✅ 完整的多模态支持（图片输入）
- ✅ 增强的工具调用流式响应
- ✅ 改进的系统提示词处理
- ✅ OpenAI SDK 完全兼容

## 11. 相关文档

- [README.md](README.md) - 项目总览
- [FEATURES_V2.md](FEATURES_V2.md) - v2.0 完整功能列表
- [API_DETAILS.md](API_DETAILS.md) - Amazon Q API 详细说明
- [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md) - Docker 部署指南

## 12. 支持

如有问题或建议，请：

1. 查看 [Issues](https://github.com/chanhanzhan/amq2api/issues)
2. 提交新的 Issue
3. 加入讨论 [Discussions](https://github.com/chanhanzhan/amq2api/discussions)

---

**注意**: 本项目将 Amazon Q API 适配为 Claude/OpenAI API 格式。实际的 AI 能力和限制仍然受 Amazon Q 服务影响。
