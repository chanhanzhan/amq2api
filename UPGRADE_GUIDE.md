# AMQ2API v2.0 升级指南

本文档详细说明如何从 v1.0 升级到 v2.0。

## 重大变更

### 1. 架构变更

**v1.0:**
- 单一账号配置（环境变量）
- 无需认证
- 仅支持 Claude API 格式

**v2.0:**
- 多账号池管理（数据库）
- 需要 API 密钥认证
- 支持 Claude + OpenAI API 格式
- Web 管理界面

### 2. 认证要求

**重要变更：** v2.0 的 API 端点需要 API 密钥认证。

原来的请求：
```bash
curl -X POST http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{...}'
```

现在需要：
```bash
curl -X POST http://localhost:8080/v1/messages \
  -H "Authorization: Bearer amq-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

### 3. 配置方式

**v1.0 配置（.env）:**
```
AMAZONQ_REFRESH_TOKEN=xxx
AMAZONQ_CLIENT_ID=xxx
AMAZONQ_CLIENT_SECRET=xxx
AMAZONQ_PROFILE_ARN=xxx
```

**v2.0 配置:**
- 账号通过 Web 界面或 API 添加到数据库
- 环境变量可选（仍支持向后兼容）

## 升级步骤

### 步骤 1: 备份现有配置

```bash
# 备份环境变量
cp .env .env.backup

# 备份 token 缓存（如果有）
cp ~/.amazonq_token_cache.json ~/.amazonq_token_cache.json.backup
```

### 步骤 2: 更新代码

```bash
# 拉取最新代码
git pull origin main

# 或者下载最新版本
# wget https://github.com/chanhanzhan/amq2api/archive/refs/heads/main.zip
```

### 步骤 3: 安装新依赖

```bash
# 激活虚拟环境
source venv/bin/activate

# 安装新依赖
pip install -r requirements.txt
```

### 步骤 4: 初始化数据库

```bash
# 数据库会自动创建，但可以手动初始化
python -c "from app.models.database import init_db; init_db()"
```

### 步骤 5: 启动新版服务

```bash
# 使用新的应用文件
python app_new.py
```

### 步骤 6: 访问管理界面

打开浏览器访问：`http://localhost:8080/admin/dashboard`

系统会提示您输入管理员 API 密钥。

**默认管理员密钥：**
```
amq-admin-default-key-change-immediately
```

输入后即可访问管理面板。

### 步骤 7: 创建新的管理员密钥并删除默认密钥

⚠️ **重要安全步骤：**

1. 在管理面板点击"API密钥"
2. 点击"+ 创建密钥"
3. 填写信息并**勾选"管理员权限"**
4. 创建后立即保存新密钥
5. 删除默认管理员密钥

或使用 API：

```bash
# 创建新的管理员密钥
curl -X POST http://localhost:8080/admin/api-keys \
  -H "Authorization: Bearer amq-admin-default-key-change-immediately" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "我的管理员密钥",
    "is_admin": true,
    "requests_per_minute": 100
  }'

# 保存新密钥后，删除默认密钥 (ID=1)
curl -X DELETE http://localhost:8080/admin/api-keys/1 \
  -H "Authorization: Bearer 你的新管理员密钥"
```

### 步骤 8: 添加账号

1. 在管理界面点击"账号管理"
2. 点击"+ 添加账号"
3. 填写以下信息（从 .env 文件复制）：
   - 名称：例如 "主账号"
   - Refresh Token：从 `AMAZONQ_REFRESH_TOKEN`
   - Client ID：从 `AMAZONQ_CLIENT_ID`
   - Client Secret：从 `AMAZONQ_CLIENT_SECRET`
   - Profile ARN：从 `AMAZONQ_PROFILE_ARN`（如果有）
   - RPM 限制：10（默认）

或者使用 API：

```bash
curl -X POST http://localhost:8080/admin/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "主账号",
    "refresh_token": "your_refresh_token_from_env",
    "client_id": "your_client_id_from_env",
    "client_secret": "your_client_secret_from_env",
    "profile_arn": "your_profile_arn_from_env",
    "requests_per_minute": 10
  }'
```

### 步骤 9: 创建 API 密钥

1. 在管理界面点击"API密钥"
2. 点击"+ 创建密钥"
3. 填写密钥信息：
   - 名称：例如 "默认密钥"
   - 描述：用途说明
   - RPM：60（推荐）
   - RPD：10000（推荐）
4. **重要：** 创建后立即保存密钥，密钥只显示一次！

或者使用 API：

```bash
curl -X POST http://localhost:8080/admin/api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "name": "默认密钥",
    "description": "用于生产环境",
    "requests_per_minute": 60,
    "requests_per_day": 10000
  }'
```

### 步骤 10: 更新客户端配置

将创建的 API 密钥添加到客户端请求中：

**Python 示例：**
```python
import requests

headers = {
    "Authorization": "Bearer amq-your-api-key-here",
    "Content-Type": "application/json"
}

response = requests.post(
    "http://localhost:8080/v1/messages",
    headers=headers,
    json={...}
)
```

**curl 示例：**
```bash
curl -X POST http://localhost:8080/v1/messages \
  -H "Authorization: Bearer amq-your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

### 步骤 11: 测试功能

```bash
# 运行测试脚本
python test_v2_features.py

# 或使用示例脚本（需要先更新 API_KEY）
python example_usage.py
```

## 向后兼容

### 保留 v1.0 功能

如果需要同时运行 v1.0 和 v2.0：

```bash
# v1.0 版本（旧版）
python main.py

# v2.0 版本（新版）
python app_new.py --port 8081
```

### 渐进式迁移

可以先在测试环境运行 v2.0，验证功能后再迁移生产环境：

```bash
# 测试环境（端口 8081）
PORT=8081 python app_new.py

# 生产环境继续使用 v1.0（端口 8080）
python main.py
```

验证无误后，停止 v1.0，启动 v2.0 在生产端口：

```bash
# 停止 v1.0
pkill -f main.py

# 启动 v2.0
PORT=8080 python app_new.py
```

## 常见问题

### Q1: 升级后原有客户端无法连接

**原因：** v2.0 需要 API 密钥认证

**解决：**
1. 在管理界面创建 API 密钥
2. 更新客户端请求，添加 Authorization 头
3. 或者临时禁用认证（不推荐）

### Q2: 数据库文件在哪里？

**位置：** `data/amq2api.db`

**备份：**
```bash
cp data/amq2api.db data/amq2api.db.backup
```

### Q3: 如何批量导入账号？

**方法 1：** 使用 API 脚本

```python
import requests

accounts = [
    {"name": "账号1", "refresh_token": "...", ...},
    {"name": "账号2", "refresh_token": "...", ...},
]

for account in accounts:
    requests.post("http://localhost:8080/admin/accounts", json=account)
```

**方法 2：** 直接操作数据库（高级）

```python
from app.models.database import SessionLocal, Account

db = SessionLocal()
account = Account(
    name="账号1",
    refresh_token="...",
    client_id="...",
    client_secret="...",
)
db.add(account)
db.commit()
```

### Q4: 如何回滚到 v1.0？

```bash
# 停止 v2.0
pkill -f app_new.py

# 启动 v1.0
python main.py

# 恢复环境变量（如果有修改）
cp .env.backup .env
```

### Q5: 性能影响如何？

**v2.0 优势：**
- 多账号负载均衡
- 更好的错误处理
- 详细的统计信息

**性能开销：**
- 数据库查询：每个请求约 1-2ms
- API 密钥验证：约 0.5ms
- 总体影响：< 5ms

对于大多数使用场景，性能影响可忽略不计。

## 高级配置

### 自定义数据库路径

```bash
DATABASE_PATH=/path/to/custom/db.sqlite python app_new.py
```

### 使用 PostgreSQL（可选）

修改 `app/models/database.py`：

```python
# 将 SQLite 改为 PostgreSQL
engine = create_engine(
    "postgresql://user:password@localhost/amq2api",
    echo=False
)
```

### Docker 部署

```bash
# 构建镜像
docker build -t amq2api:v2 .

# 运行容器
docker run -d \
  -p 8080:8080 \
  -v ./data:/app/data \
  -e PORT=8080 \
  amq2api:v2 python app_new.py
```

## 获取帮助

- 查看文档：[FEATURES_V2.md](FEATURES_V2.md)
- 问题反馈：[GitHub Issues](https://github.com/chanhanzhan/amq2api/issues)
- 功能建议：[GitHub Discussions](https://github.com/chanhanzhan/amq2api/discussions)

## 总结

升级到 v2.0 后，您将获得：
- ✅ 多账号池管理
- ✅ 安全的 API 密钥认证
- ✅ OpenAI API 兼容性
- ✅ Web 管理界面
- ✅ 详细的使用统计

如有任何问题，请参考文档或提交 Issue。
