#!/usr/bin/env python3
"""
AMQ2API v2.0 使用示例
演示如何使用账号池和 API 密钥功能
"""
import requests
import json

# 配置
BASE_URL = "http://localhost:8080"
API_KEY = "amq-your-api-key-here"  # 从管理界面创建

def example_claude_api():
    """Claude API 格式示例"""
    print("=== Claude API 示例 ===")
    
    url = f"{BASE_URL}/v1/messages"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "claude-sonnet-4.5",
        "messages": [
            {
                "role": "user",
                "content": "你好，请用一句话介绍你自己"
            }
        ],
        "max_tokens": 1024,
        "stream": True
    }
    
    response = requests.post(url, headers=headers, json=data, stream=True)
    
    if response.status_code == 200:
        print("响应:")
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    print(line_str[6:])
    else:
        print(f"错误: {response.status_code}")
        print(response.text)


def example_openai_api():
    """OpenAI API 格式示例"""
    print("\n=== OpenAI API 示例 ===")
    
    url = f"{BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant"
            },
            {
                "role": "user",
                "content": "Say hello in Chinese"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
        "stream": True
    }
    
    response = requests.post(url, headers=headers, json=data, stream=True)
    
    if response.status_code == 200:
        print("响应:")
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    print(line_str[6:])
    else:
        print(f"错误: {response.status_code}")
        print(response.text)


def manage_accounts():
    """账号管理示例"""
    print("\n=== 账号管理示例 ===")
    
    # 列出账号
    url = f"{BASE_URL}/admin/accounts"
    response = requests.get(url)
    
    if response.status_code == 200:
        accounts = response.json()
        print(f"当前有 {len(accounts)} 个账号:")
        for acc in accounts:
            print(f"  - {acc['name']}: {'活跃' if acc['is_active'] else '停用'}, "
                  f"{'健康' if acc['is_healthy'] else '异常'}, "
                  f"请求数: {acc['total_requests']}")
    
    # 添加账号示例（需要替换为实际凭证）
    # new_account = {
    #     "name": "测试账号",
    #     "refresh_token": "your_refresh_token",
    #     "client_id": "your_client_id",
    #     "client_secret": "your_client_secret",
    #     "requests_per_minute": 10
    # }
    # response = requests.post(url, json=new_account)
    # if response.status_code == 200:
    #     print("账号添加成功!")


def manage_api_keys():
    """API 密钥管理示例"""
    print("\n=== API 密钥管理示例 ===")
    
    # 列出密钥
    url = f"{BASE_URL}/admin/api-keys"
    response = requests.get(url)
    
    if response.status_code == 200:
        keys = response.json()
        print(f"当前有 {len(keys)} 个 API 密钥:")
        for key in keys:
            print(f"  - {key['name']}: {'活跃' if key['is_active'] else '停用'}, "
                  f"请求数: {key['total_requests']}")
    
    # 创建密钥示例
    # new_key = {
    #     "name": "测试密钥",
    #     "description": "用于测试",
    #     "requests_per_minute": 60,
    #     "requests_per_day": 10000
    # }
    # response = requests.post(url, json=new_key)
    # if response.status_code == 200:
    #     result = response.json()
    #     print(f"密钥创建成功! Key: {result['key']}")
    #     print("请妥善保存，密钥只显示一次!")


def check_health():
    """健康检查"""
    print("\n=== 健康检查 ===")
    
    url = f"{BASE_URL}/health"
    response = requests.get(url)
    
    if response.status_code == 200:
        health = response.json()
        print(f"状态: {health['status']}")
        print(f"活跃账号: {health.get('active_accounts', 0)}")
        print(f"活跃密钥: {health.get('active_api_keys', 0)}")
        print(f"版本: {health.get('version', 'unknown')}")


def main():
    """主函数"""
    print("AMQ2API v2.0 使用示例")
    print("=" * 50)
    
    # 检查服务健康
    check_health()
    
    # 管理示例（不需要 API 密钥）
    manage_accounts()
    manage_api_keys()
    
    # API 调用示例（需要 API 密钥）
    if API_KEY != "amq-your-api-key-here":
        example_claude_api()
        example_openai_api()
    else:
        print("\n⚠️  请先在管理界面创建 API 密钥，并更新脚本中的 API_KEY 变量")
        print(f"   访问: {BASE_URL}/admin/dashboard")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到服务器: {BASE_URL}")
        print("   请确保服务已启动")
    except Exception as e:
        print(f"❌ 错误: {e}")
