# 安全建议

本文档提供 AMQ2API v2.0 的安全配置和最佳实践建议。

## 管理员账号安全

### 修改默认密码

**⚠️ 非常重要：** 首次部署后必须立即修改默认管理员密码。

默认凭据：
- 用户名：`admin`
- 密码：`admin123`

**修改方法：**

1. 登录管理界面
2. 使用 API 修改密码：

```bash
# 首先登录获取 session cookie
curl -c cookies.txt -X POST http://localhost:8080/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 修改密码
curl -b cookies.txt -X POST http://localhost:8080/admin/change-password \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "admin123",
    "new_password": "YourSecurePassword123!"
  }'
```

### 密码要求建议

- 最少 12 个字符
- 包含大小写字母
- 包含数字
- 包含特殊字符
- 不使用常见密码或个人信息

### 会话安全

- **会话有效期：** 24小时
- **不活动超时：** 2小时
- **Cookie 设置：** HTTP-only, SameSite=Lax
- **会话存储：** 数据库（非内存）

**最佳实践：**
- 使用后及时登出
- 不要在公共计算机上保持登录状态
- 定期检查活跃会话

## API 密钥安全

### 密钥管理

1. **安全生成**
   - 使用管理界面生成密钥
   - 密钥格式：`amq-` + 48字节随机字符串
   - 密钥只在创建时显示一次

2. **妥善保管**
   ```bash
   # 使用环境变量存储
   export AMQ_API_KEY="amq-your-api-key-here"
   
   # 不要硬编码在代码中
   # 不要提交到版本控制系统
   ```

3. **定期轮换**
   - 建议每 90 天轮换一次
   - 发生安全事件后立即轮换
   - 旧密钥应立即吊销

4. **权限控制**
   - 为不同用途创建不同的 API 密钥
   - 设置合理的速率限制
   - 使用 `expires_at` 设置过期时间

### 速率限制

**推荐配置：**

```json
{
  "requests_per_minute": 60,    // 每分钟最多 60 请求
  "requests_per_day": 10000     // 每天最多 10000 请求
}
```

**根据用途调整：**
- 生产环境：严格限制
- 开发环境：宽松限制
- 临时测试：短期有效期

## 账号池安全

### 账号凭据保护

1. **加密存储**
   - 数据库文件权限：仅所有者可读写 (600)
   - 考虑使用加密文件系统
   - 定期备份数据库

2. **账号隔离**
   - 不同环境使用不同账号
   - 生产/测试/开发环境分离
   - 限制每个账号的 RPM

3. **健康监控**
   - 定期检查账号状态
   - 异常时发送告警
   - 自动禁用异常账号

### 凭据轮换

```bash
# 更新账号凭据
curl -X PUT http://localhost:8080/admin/accounts/1 \
  -H "Content-Type: application/json" \
  -b "admin_session=your-session" \
  -d '{
    "refresh_token": "new_refresh_token",
    "client_secret": "new_client_secret"
  }'
```

## 网络安全

### 生产部署

1. **HTTPS/TLS**
   ```bash
   # 使用 Nginx 作为反向代理
   server {
       listen 443 ssl;
       server_name your-domain.com;
       
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       
       location / {
           proxy_pass http://localhost:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

2. **防火墙规则**
   ```bash
   # 仅允许特定 IP 访问管理界面
   iptables -A INPUT -p tcp --dport 8080 -s trusted-ip -j ACCEPT
   iptables -A INPUT -p tcp --dport 8080 -j DROP
   ```

3. **访问控制**
   - 管理界面仅限内网访问
   - API 端点使用 API 密钥认证
   - 考虑使用 VPN 或 IP 白名单

### Docker 安全

```dockerfile
# 使用非 root 用户运行
FROM python:3.11-slim
RUN useradd -m -u 1000 appuser
USER appuser

# 只暴露必要端口
EXPOSE 8080

# 使用只读文件系统（除了数据目录）
docker run --read-only \
  -v ./data:/app/data \
  amq2api:v2
```

## 数据安全

### 数据库安全

1. **文件权限**
   ```bash
   chmod 600 data/amq2api.db
   chown appuser:appgroup data/amq2api.db
   ```

2. **定期备份**
   ```bash
   # 每日备份脚本
   #!/bin/bash
   DATE=$(date +%Y%m%d)
   cp data/amq2api.db backups/amq2api-$DATE.db
   
   # 加密备份
   gpg -c backups/amq2api-$DATE.db
   
   # 清理旧备份（保留 30 天）
   find backups/ -name "*.db" -mtime +30 -delete
   ```

3. **敏感数据加密**
   考虑使用工具如 `sqlcipher` 加密整个数据库：
   ```python
   from sqlalchemy import create_engine
   
   engine = create_engine(
       'sqlite+pysqlcipher:///:memory:',
       connect_args={'check_same_thread': False},
       echo=False
   )
   ```

### 日志安全

1. **脱敏处理**
   - 不记录完整的 API 密钥（仅前10位）
   - 不记录密码
   - 不记录完整的 refresh token

2. **日志轮转**
   ```python
   # 配置日志轮转
   from logging.handlers import RotatingFileHandler
   
   handler = RotatingFileHandler(
       'logs/amq2api.log',
       maxBytes=10485760,  # 10MB
       backupCount=10
   )
   ```

3. **访问控制**
   ```bash
   chmod 640 logs/*.log
   chown appuser:loggroup logs/*.log
   ```

## 监控和审计

### 安全事件监控

监控以下事件：
- 失败的登录尝试
- API 密钥使用异常
- 账号健康状态变化
- 异常的请求模式

### 审计日志

记录关键操作：
- 管理员登录/登出
- API 密钥创建/删除
- 账号添加/删除/修改
- 配置更改

### 告警设置

```bash
# 示例：检测异常登录尝试
if [ $(grep "Login failed" logs/amq2api.log | wc -l) -gt 10 ]; then
    echo "Warning: Multiple failed login attempts detected"
    # 发送告警邮件/短信
fi
```

## 合规性

### 数据保护

1. **GDPR/CCPA 合规**
   - 定期清理不活跃账号
   - 提供数据导出功能
   - 实施数据保留政策

2. **PCI DSS（如适用）**
   - 不存储信用卡信息
   - 使用强加密
   - 定期安全审计

### 密码策略

```python
# 实施密码强度要求
def validate_password(password):
    if len(password) < 12:
        return False, "密码至少需要12个字符"
    if not re.search(r'[A-Z]', password):
        return False, "密码需要包含大写字母"
    if not re.search(r'[a-z]', password):
        return False, "密码需要包含小写字母"
    if not re.search(r'[0-9]', password):
        return False, "密码需要包含数字"
    if not re.search(r'[!@#$%^&*]', password):
        return False, "密码需要包含特殊字符"
    return True, ""
```

## 应急响应

### 安全事件处理

1. **发现未授权访问**
   ```bash
   # 立即吊销所有 API 密钥
   sqlite3 data/amq2api.db "UPDATE api_keys SET is_active = 0"
   
   # 清除所有会话
   sqlite3 data/amq2api.db "DELETE FROM admin_sessions"
   
   # 更改管理员密码
   ```

2. **数据泄露**
   - 立即轮换所有凭据
   - 通知受影响用户
   - 分析泄露范围
   - 加强安全措施

3. **系统被入侵**
   - 立即断开网络
   - 保存日志和证据
   - 从备份恢复
   - 进行完整安全审计

## 定期安全检查清单

### 每周
- [ ] 检查失败登录日志
- [ ] 审查 API 使用统计
- [ ] 检查账号健康状态

### 每月
- [ ] 轮换测试环境 API 密钥
- [ ] 审查活跃会话列表
- [ ] 检查数据库备份

### 每季度
- [ ] 轮换生产环境 API 密钥
- [ ] 更新依赖包
- [ ] 进行安全审计
- [ ] 审查和更新安全策略

### 每年
- [ ] 更改所有管理员密码
- [ ] 全面安全评估
- [ ] 更新灾难恢复计划
- [ ] 员工安全培训

## 获取帮助

如果发现安全漏洞，请负责任地披露：
- 不要公开发布漏洞详情
- 通过私密渠道联系维护者
- 给予合理的修复时间
- 协助验证修复方案

---

**记住：安全是一个持续的过程，不是一次性的任务！**
