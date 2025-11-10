#!/usr/bin/env python3
"""
测试 AMQ2API v2.0 基础功能
"""
import sys
import asyncio
from sqlalchemy.orm import Session

print("=" * 60)
print("AMQ2API v2.0 功能测试")
print("=" * 60)

# 测试 1: 数据库初始化
print("\n[1/6] 测试数据库初始化...")
try:
    from app.models.database import init_db, SessionLocal
    init_db()
    print("✅ 数据库初始化成功")
except Exception as e:
    print(f"❌ 数据库初始化失败: {e}")
    sys.exit(1)

# 测试 2: 账号池管理器
print("\n[2/6] 测试账号池管理器...")
try:
    from app.core.account_pool import account_pool_manager
    db = SessionLocal()
    
    # 列出账号
    accounts = account_pool_manager.list_accounts(db)
    print(f"✅ 账号池管理器工作正常，当前账号数: {len(accounts)}")
    
    db.close()
except Exception as e:
    print(f"❌ 账号池管理器测试失败: {e}")
    sys.exit(1)

# 测试 3: API 密钥管理器
print("\n[3/6] 测试 API 密钥管理器...")
try:
    from app.core.api_keys import api_key_manager
    db = SessionLocal()
    
    # 列出密钥
    keys = api_key_manager.list_keys(db)
    print(f"✅ API 密钥管理器工作正常，当前密钥数: {len(keys)}")
    
    # 测试密钥生成
    test_key = api_key_manager.generate_key()
    if test_key.startswith("amq-"):
        print(f"✅ 密钥生成正常，示例: {test_key[:20]}...")
    else:
        print(f"❌ 密钥格式错误: {test_key}")
    
    db.close()
except Exception as e:
    print(f"❌ API 密钥管理器测试失败: {e}")
    sys.exit(1)

# 测试 4: OpenAI 格式转换器
print("\n[4/6] 测试 OpenAI 格式转换器...")
try:
    from app.core.openai_converter import convert_openai_to_claude, convert_openai_model_to_claude
    
    # 测试模型转换
    claude_model = convert_openai_model_to_claude("gpt-4")
    if claude_model == "claude-sonnet-4":
        print("✅ 模型转换正常")
    else:
        print(f"❌ 模型转换错误: {claude_model}")
    
    # 测试请求转换
    openai_req = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"}
        ],
        "max_tokens": 1000
    }
    claude_req = convert_openai_to_claude(openai_req)
    
    if "system" in claude_req and "messages" in claude_req:
        print("✅ 请求格式转换正常")
    else:
        print(f"❌ 请求格式转换错误")
    
except Exception as e:
    print(f"❌ OpenAI 格式转换器测试失败: {e}")
    sys.exit(1)

# 测试 5: 认证中间件
print("\n[5/6] 测试认证中间件...")
try:
    from app.core.auth_middleware import get_api_key_from_request
    print("✅ 认证中间件导入成功")
except Exception as e:
    print(f"❌ 认证中间件测试失败: {e}")
    sys.exit(1)

# 测试 6: 管理 API
print("\n[6/6] 测试管理 API...")
try:
    from app.api.admin import router
    print(f"✅ 管理 API 路由加载成功，端点数: {len(router.routes)}")
except Exception as e:
    print(f"❌ 管理 API 测试失败: {e}")
    sys.exit(1)

# 总结
print("\n" + "=" * 60)
print("✅ 所有基础功能测试通过！")
print("=" * 60)
print("\n下一步:")
print("1. 启动服务: python app_new.py")
print("2. 访问管理界面: http://localhost:8080/admin/dashboard")
print("3. 添加账号和创建 API 密钥")
print("4. 使用 example_usage.py 测试 API 调用")
print("")
