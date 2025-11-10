# Amazon Q to Claude/OpenAI API Proxy

将 Claude/OpenAI API 请求转换为 Amazon Q/CodeWhisperer 请求的代理服务，支持账号池管理、API 密钥认证和 Web 管理界面。

[![Docker Build](https://github.com/yourusername/amq2api/actions/workflows/docker-build.yml/badge.svg)](https://github.com/yourusername/amq2api/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎉 v2.0 新功能

- ✅ **账号池管理** - 支持多个 Amazon Q 账号，自动负载均衡和故障转移
- ✅ **API 密钥认证** - 安全的访问控制，支持多密钥管理和限流
- ✅ **OpenAI API 支持** - 完整支持 OpenAI chat completion 格式（流式/非流式）
- ✅ **Web 管理界面** - 现代化的管理面板，实时监控和统计
- ✅ **使用统计** - 详细的请求和 token 使用统计，支持图表可视化
- ✅ **自动 Token 刷新** - 后台自动刷新到期账号的 token
- ✅ **健康检查** - 自动检测账号健康状态，异常账号自动隔离

---

## 功能特性

### 核心功能
- ✅ 完整的 Claude API 兼容接口 (`/v1/messages`)
- ✅ 完整的 OpenAI API 兼容接口 (`/v1/chat/completions`)
- ✅ 自动 Token 刷新机制（提前 5 分钟刷新）
- ✅ SSE 流式响应支持
- ✅ 非流式响应支持
- ✅ 请求/响应格式自动转换
- ✅ 完善的错误处理和日志

### 账号池功能
- ✅ 多账号负载均衡（轮询算法）
- ✅ 账号健康检查（自动隔离异常账号）
- ✅ 自动故障恢复（30 分钟后重试）
- ✅ 请求限流（每分钟请求数限制）
- ✅ 账号使用统计

### 管理功能
- ✅ Web 管理界面（账号管理、API 密钥管理）
- ✅ 使用统计（tokens、请求数、账号使用情况）
- ✅ 图表可视化（tokens 使用趋势）
- ✅ 账号健康监控
- ✅ JSON 文件批量导入账号

## 架构说明

### 请求流程（v2.0）
```
Claude/OpenAI API 请求
    ↓
app_new.py (FastAPI 服务器)
    ├─→ API 密钥验证 (auth_middleware.py)
    ├─→ 账号池选择 (account_pool.py)
    ├─→ Token 刷新 (auth.py + redis_cache.py)
    ├─→ 请求转换 (converter.py / openai_converter.py)
    ↓
Amazon Q API
    ↓
Event Stream 响应
    ↓
event_stream_parser.py → parser.py → stream_handler_new.py
    ↓
Claude/OpenAI 格式 SSE 响应
    ↓
使用日志记录 (UsageLog)
```

### 核心模块

#### v2.0 新模块
- **app_new.py** - FastAPI 服务器，处理所有 API 端点
- **app/core/account_pool.py** - 账号池管理和负载均衡
- **app/core/api_keys.py** - API 密钥管理
- **app/core/auth_middleware.py** - API 密钥认证中间件
- **app/core/openai_converter.py** - OpenAI 格式转换
- **app/core/redis_cache.py** - Redis Token 缓存
- **app/api/admin.py** - 管理 API 端点
- **app/models/database.py** - 数据库模型（账号、API 密钥、使用日志）

#### 原有模块
- **converter.py** - Claude 请求格式转换 (Claude → Amazon Q)
- **event_stream_parser.py** - 解析 AWS Event Stream 二进制格式
- **parser.py** - 事件类型转换 (Amazon Q → Claude)
- **stream_handler_new.py** - 流式响应处理和事件生成
- **message_processor.py** - 历史消息合并，确保 user-assistant 交替
- **auth.py** - Token 自动刷新机制
- **config.py** - 配置管理和 Token 缓存
- **models.py** - 数据结构定义

## 快速开始

### 使用 Docker（推荐）

#### 方式一：使用 Docker Compose

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 Amazon Q 凭证

# 2. 启动服务
docker compose up -d

# 3. 验证
curl http://localhost:8080/health
```

#### 方式二：使用预构建镜像

```bash
# 从 GitHub Container Registry 拉取镜像
docker pull ghcr.io/yourusername/amq2api:latest

# 运行容器
docker run -d \
  --name amq2api \
  -p 8080:8080 \
  -e AMAZONQ_REFRESH_TOKEN=your_refresh_token \
  -e AMAZONQ_CLIENT_ID=your_client_id \
  -e AMAZONQ_CLIENT_SECRET=your_client_secret \
  -v amq2api_data:/app/data \
  ghcr.io/yourusername/amq2api:latest
```

#### 方式三：从源码构建

```bash
# 克隆仓库
git clone https://github.com/yourusername/amq2api.git
cd amq2api

# 构建镜像
docker build -t amq2api:latest .

# 运行容器
docker run -d \
  --name amq2api \
  -p 8080:8080 \
  -e AMAZONQ_REFRESH_TOKEN=your_refresh_token \
  -e AMAZONQ_CLIENT_ID=your_client_id \
  -e AMAZONQ_CLIENT_SECRET=your_client_secret \
  -v amq2api_data:/app/data \
  amq2api:latest
```

📖 **详细的 Docker 部署文档：[DOCKER_DEPLOY.md](DOCKER_DEPLOY.md)**

### 本地部署

#### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填写以下信息：
# - AMAZONQ_REFRESH_TOKEN: 你的 Amazon Q refresh token
# - AMAZONQ_CLIENT_ID: 客户端 ID
# - AMAZONQ_CLIENT_SECRET: 客户端密钥
# - AMAZONQ_PROFILE_ARN: Profile ARN（组织账号需要，个人账号留空）
# - PORT: 服务端口（默认 8080）
```

#### 3. 初始化数据库

```bash
# 数据库会在首次运行时自动创建
# 如果需要手动初始化，可以运行：
python3 -c "from app.models.database import init_db; init_db()"
```

#### 4. 启动服务

```bash
# 使用启动脚本（推荐）
chmod +x start.sh
./start.sh

# 或直接运行
python3 app_new.py
```

#### 5. 访问管理界面

```bash
# 打开浏览器访问
http://localhost:8080/admin/login

# 首次登录需要使用默认管理员密钥（查看启动日志）
# 登录后请立即创建新的管理员密钥并删除默认密钥
```

#### 6. 测试服务

```bash
# 健康检查
curl http://localhost:8080/health

# 发送测试请求
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [
      {
        "role": "user",
        "content": "Hello, how are you?"
      }
    ],
    "max_tokens": 1024,
    "stream": true
  }'
```

## 配置说明

### 环境变量

#### 必需配置（单账号模式）
| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `AMAZONQ_REFRESH_TOKEN` | ✅ | - | Amazon Q 刷新令牌 |
| `AMAZONQ_CLIENT_ID` | ✅ | - | 客户端 ID |
| `AMAZONQ_CLIENT_SECRET` | ✅ | - | 客户端密钥 |

#### 可选配置
| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `AMAZONQ_PROFILE_ARN` | ❌ | 空 | Profile ARN（组织账号） |
| `PORT` | ❌ | 8080 | 服务监听端口 |
| `AMAZONQ_API_ENDPOINT` | ❌ | https://q.us-east-1.amazonaws.com/ | API 端点 |
| `AMAZONQ_TOKEN_ENDPOINT` | ❌ | https://oidc.us-east-1.amazonaws.com/token | Token 端点 |
| `DATABASE_PATH` | ❌ | data/amq2api.db | SQLite 数据库路径 |
| `REDIS_URL` | ❌ | - | Redis 连接 URL（用于 Token 缓存，可选） |

> **注意**：v2.0 支持账号池模式，可以通过 Web 管理界面添加多个账号，无需在环境变量中配置。环境变量配置仅用于单账号模式或初始化第一个账号。

## API 接口

### Claude API 兼容接口

#### POST /v1/messages

创建消息（Claude API 兼容）

**认证：** 需要在请求头中提供 API 密钥
```
Authorization: Bearer <your_api_key>
```

**请求体：**

```json
{
  "model": "claude-sonnet-4.5",
  "messages": [
    {
      "role": "user",
      "content": "你好"
    }
  ],
  "max_tokens": 4096,
  "temperature": 0.7,
  "stream": true,
  "system": "你是一个有帮助的助手"
}
```

**响应：**

流式 SSE 响应，格式与 Claude API 完全兼容。

### OpenAI API 兼容接口

#### POST /v1/chat/completions

创建聊天完成（OpenAI API 兼容）

**认证：** 需要在请求头中提供 API 密钥
```
Authorization: Bearer <your_api_key>
```

**请求体：**

```json
{
  "model": "gpt-4",
  "messages": [
    {
      "role": "user",
      "content": "Hello, how are you?"
    }
  ],
  "max_tokens": 1024,
  "temperature": 0.7,
  "stream": true
}
```

**响应：**

流式或非流式响应，格式与 OpenAI API 完全兼容。

#### GET /v1/models

列出可用模型

**响应：**

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-sonnet-4.5",
      "object": "model",
      "created": 1234567890,
      "owned_by": "anthropic"
    },
    ...
  ]
}
```

### 管理接口

#### GET /health

健康检查端点

**响应：**

```json
{
  "status": "healthy",
  "active_accounts": 3,
  "active_api_keys": 5,
  "version": "2.0.0"
}
```

#### Web 管理界面

- **GET /admin/login** - 登录页面
- **GET /admin/dashboard** - 管理面板（需要管理员 API 密钥）

所有管理 API 端点都需要管理员 API 密钥认证，详见 [API_DETAILS.md](API_DETAILS.md)。

## 工作流程

```
Claude Code 客户端
    ↓
    ↓ Claude API 格式请求
    ↓
代理服务 (main.py)
    ↓
    ├─→ 认证 (auth.py)
    │   └─→ 刷新 Token（如需要）
    ↓
    ├─→ 转换请求 (converter.py)
    │   └─→ Claude 格式 → CodeWhisperer 格式
    ↓
    ├─→ 发送到 Amazon Q API
    ↓
    ├─→ 接收 SSE 流
    ↓
    ├─→ 解析事件 (parser.py)
    │   └─→ CodeWhisperer 事件 → Claude 事件
    ↓
    ├─→ 流处理 (stream_handler.py)
    │   └─→ 累积响应、计算 tokens
    ↓
    └─→ 返回 Claude 格式 SSE 流
        ↓
Claude Code 客户端
```

## 使用指南

### 首次使用

1. **启动服务**后访问 `http://localhost:8080/admin/login`
2. **登录**：使用默认管理员密钥（查看启动日志）
3. **创建账号**：
   - 方式一：通过 Web 界面手动添加
   - 方式二：上传 AWS SSO JSON 文件（推荐）
4. **创建 API 密钥**：在管理界面创建新的 API 密钥
5. **删除默认密钥**：安全起见，删除默认管理员密钥

### 账号管理

- **添加账号**：支持手动添加或 JSON 文件批量导入
- **健康检查**：系统自动检测账号健康状态
- **故障恢复**：异常账号会在 30 分钟后自动重试
- **负载均衡**：多个账号自动轮询分配请求

### API 使用

#### 使用 Claude API 格式

```bash
curl -X POST http://localhost:8080/v1/messages \
  -H "Authorization: Bearer <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

#### 使用 OpenAI API 格式

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": true
  }'
```

## 注意事项

1. **Token 管理**
   - access_token 会自动刷新（提前 5 分钟）
   - Token 缓存在 Redis 或本地文件系统
   - 账号池模式下，每个账号独立管理 token

2. **流式/非流式响应**
   - 支持流式响应（`stream: true`）
   - 支持非流式响应（`stream: false`）
   - OpenAI API 格式两种模式都支持

3. **Token 计数**
   - 使用 tiktoken 进行精确 token 计数
   - 自动记录输入/输出 tokens 到使用日志
   - 支持在管理界面查看详细统计

4. **错误处理**
   - 所有错误都会记录到日志
   - HTTP 错误会返回适当的状态码
   - 上游 API 错误会透传给客户端
   - 账号异常会自动隔离，不影响其他账号

5. **数据持久化**
   - SQLite 数据库存储账号、API 密钥和使用日志
   - 建议定期备份 `data/amq2api.db` 文件
   - Token 缓存建议使用 Redis（可选）

## CI/CD 和自动化构建

### GitHub Actions 工作流

项目包含自动化的 Docker 镜像构建工作流：

- **触发条件**：
  - 推送到 `main` 或 `master` 分支
  - 创建版本标签（`v*`）
  - 手动触发（workflow_dispatch）
  - Pull Request（仅构建，不推送）

- **构建特性**：
  - 多平台支持（linux/amd64, linux/arm64）
  - 构建缓存优化
  - 自动推送到 GitHub Container Registry
  - 自动生成镜像标签（latest, branch, sha, semver）

### 使用预构建镜像

```bash
# 拉取最新版本
docker pull ghcr.io/yourusername/amq2api:latest

# 拉取特定版本
docker pull ghcr.io/yourusername/amq2api:v2.0.0

# 拉取特定分支
docker pull ghcr.io/yourusername/amq2api:main-abc1234
```

### 本地构建

```bash
# 构建镜像
docker build -t amq2api:latest .

# 构建多平台镜像（需要 buildx）
docker buildx build --platform linux/amd64,linux/arm64 -t amq2api:latest .
```

## 开发说明

### 项目结构

```
amq2api/
├── .github/
│   └── workflows/
│       └── docker-build.yml    # CI/CD 工作流
├── app/
│   ├── api/
│   │   └── admin.py            # 管理 API 端点
│   ├── core/
│   │   ├── account_pool.py      # 账号池管理
│   │   ├── api_keys.py         # API 密钥管理
│   │   ├── auth_middleware.py  # 认证中间件
│   │   ├── openai_converter.py # OpenAI 格式转换
│   │   └── redis_cache.py      # Redis 缓存
│   ├── models/
│   │   └── database.py         # 数据库模型
│   └── web/
│       ├── static/
│       │   └── admin.js         # 管理界面 JS
│       └── templates/
│           ├── admin.html       # 管理面板
│           └── login.html      # 登录页面
├── data/                        # 数据目录（SQLite 数据库）
├── .env.example                 # 环境变量模板
├── Dockerfile                   # Docker 镜像构建
├── docker-compose.yml           # Docker Compose 配置
├── app_new.py                   # 主服务（v2.0）
├── auth.py                      # Token 刷新
├── converter.py                 # Claude 请求转换
├── parser.py                    # 事件解析
├── stream_handler_new.py        # 流处理
└── requirements.txt             # Python 依赖
```

### 扩展功能

如需添加新功能，可以：

1. **添加新的事件类型**
   - 在 `models.py` 中定义新的事件结构
   - 在 `parser.py` 中添加解析逻辑
   - 在 `stream_handler.py` 中添加处理逻辑

2. **支持非流式响应**
   - 在 `main.py` 中实现非流式响应逻辑
   - 累积完整响应后一次性返回

3. **添加缓存**
   - 实现对话历史缓存
   - 减少重复请求

## 故障排查

### 问题：Token 刷新失败

**症状：** 账号显示为不健康状态，错误信息包含 "Token refresh failed"

**解决方案：**
- 检查账号的 `refresh_token`、`client_id`、`client_secret` 是否正确
- 在管理界面点击"刷新 Token"按钮手动刷新
- 查看日志中的详细错误信息
- 确认账号是否被 AWS 限制或禁用

### 问题：上游 API 返回错误

**症状：** 请求返回 4xx 或 5xx 错误

**解决方案：**
- 检查 `AMAZONQ_API_ENDPOINT` 是否正确
- 检查网络连接
- 查看日志中的详细错误信息
- 检查账号是否达到请求限制

### 问题：流式响应中断

**症状：** 流式响应中途断开

**解决方案：**
- 检查网络稳定性
- 增加超时时间（默认 300 秒）
- 查看日志中的错误信息
- 检查账号健康状态

### 问题：无法访问管理界面

**症状：** 访问 `/admin/login` 返回 401 或 403

**解决方案：**
- 确认已创建管理员 API 密钥
- 检查 API 密钥是否已激活
- 清除浏览器缓存和 localStorage
- 查看浏览器控制台的错误信息

### 问题：账号池无可用账号

**症状：** 请求返回 "No available accounts in pool"

**解决方案：**
- 在管理界面检查账号状态
- 确保至少有一个账号处于"活跃"和"健康"状态
- 检查账号的请求限流设置
- 手动刷新异常账号的 Token

## 版本历史

### v2.0.0
- ✅ 账号池管理功能
- ✅ API 密钥认证系统
- ✅ OpenAI API 兼容接口
- ✅ Web 管理界面
- ✅ 使用统计和可视化
- ✅ 自动 Token 刷新
- ✅ 健康检查和故障恢复

### v1.0.0
- ✅ Claude API 兼容接口
- ✅ 流式响应支持
- ✅ 自动 Token 刷新

详细变更日志请查看 [CHANGELOG.md](CHANGELOG.md)

## 相关文档

- [API_DETAILS.md](API_DETAILS.md) - API 详细说明
- [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md) - Docker 部署指南
- [CLAUDE.md](CLAUDE.md) - 开发指南

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

### 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 支持

如有问题或建议，请：
- 提交 [Issue](https://github.com/yourusername/amq2api/issues)
- 查看 [文档](https://github.com/yourusername/amq2api/wiki)
