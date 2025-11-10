"""
新的主应用文件
整合账号池管理、API密钥认证、OpenAI API支持和Web管理界面
"""
import logging
import httpx
import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from datetime import datetime

from config import read_global_config, get_config_sync
from auth import get_auth_headers
from models import ClaudeRequest
from converter import convert_claude_to_codewhisperer_request, codewhisperer_request_to_dict
from stream_handler_new import handle_amazonq_stream
from message_processor import process_claude_history_for_amazonq, log_history_summary

# New imports for account pool and auth
from app.models.database import init_db, get_db, SessionLocal
from app.core.account_pool import account_pool_manager
from app.core.api_keys import api_key_manager
from app.core.auth_middleware import verify_api_key
from app.core.openai_converter import convert_openai_to_claude, convert_claude_to_openai_stream, convert_claude_to_openai_non_stream
from app.api.admin import router as admin_router
from app.core.admin_api_auth import get_admin_api_key

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 模板目录
templates = Jinja2Templates(directory="app/web/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    import asyncio
    from datetime import datetime, timedelta
    
    # 启动时初始化
    logger.info("正在初始化应用...")
    
    # 初始化数据库
    logger.info("初始化数据库...")
    init_db()
    
    # 初始化配置
    logger.info("初始化配置...")
    try:
        await read_global_config()
        logger.info("配置初始化成功")
    except Exception as e:
        logger.warning(f"配置初始化警告: {e} (在使用账号池模式时这是正常的)")
    
    # 启动后台任务：自动刷新到期账号
    async def auto_refresh_tokens_task():
        """后台任务：自动刷新到期账号的 token"""
        from app.core.redis_cache import get_token_cache, delete_token_cache, set_token_cache
        from auth import refresh_token_for_account
        
        while True:
            try:
                # 每 5 分钟检查一次
                await asyncio.sleep(300)
                
                db = SessionLocal()
                try:
                    # 获取所有活跃账号
                    accounts = account_pool_manager.list_accounts(db, active_only=True)
                    
                    for account in accounts:
                        try:
                            # 检查 token 缓存
                            token_cache = get_token_cache(str(account.id))
                            
                            should_refresh = False
                            if not token_cache:
                                # 没有缓存，需要刷新
                                should_refresh = True
                                logger.info(f"账号 {account.name} 没有 token 缓存，准备刷新")
                            else:
                                # 检查是否即将过期（提前 5 分钟刷新）
                                expires_at = datetime.fromisoformat(token_cache['expires_at'])
                                now = datetime.now()
                                
                                # 如果 token 在 5 分钟内过期，或者已经过期，则刷新
                                if now >= (expires_at - timedelta(minutes=5)):
                                    should_refresh = True
                                    logger.info(f"账号 {account.name} token 即将过期（{expires_at}），准备刷新")
                            
                            if should_refresh:
                                # 删除旧缓存
                                delete_token_cache(str(account.id))
                                
                                # 刷新 token
                                try:
                                    token_data = await refresh_token_for_account(
                                        account.refresh_token,
                                        account.client_id,
                                        account.client_secret,
                                        account_id=str(account.id)
                                    )
                                    
                                    # 更新账号健康状态
                                    account_pool_manager.update_health_status(db, account.id, True, None)
                                    
                                    logger.info(f"账号 {account.name} token 自动刷新成功")
                                
                                except Exception as e:
                                    logger.error(f"账号 {account.name} token 自动刷新失败: {e}")
                                    account_pool_manager.update_health_status(
                                        db, account.id, False, f"Auto refresh failed: {str(e)}"
                                    )
                        
                        except Exception as e:
                            logger.error(f"处理账号 {account.id} 时发生错误: {e}", exc_info=True)
                            continue
                
                finally:
                    db.close()
            
            except Exception as e:
                logger.error(f"自动刷新 token 任务发生错误: {e}", exc_info=True)
                # 发生错误时等待更长时间再重试
                await asyncio.sleep(60)
    
    # 启动后台任务
    task = asyncio.create_task(auto_refresh_tokens_task())
    logger.info("后台任务：自动刷新到期账号 token 已启动")
    
    logger.info("应用启动完成")
    yield
    
    # 关闭时清理资源
    logger.info("正在关闭服务...")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("后台任务已停止")


# 创建 FastAPI 应用
app = FastAPI(
    title="Amazon Q to Claude/OpenAI API Proxy",
    description="将 Claude/OpenAI API 请求转换为 Amazon Q 请求的代理服务，支持账号池管理",
    version="2.0.0",
    lifespan=lifespan
)

# 挂载静态文件
os.makedirs("app/web/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# 包含路由
app.include_router(admin_router)


@app.get("/")
async def root():
    """根路径重定向到登录页面"""
    return RedirectResponse(url="/admin/login")


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request):
    """登录页面（不需要认证）"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """管理面板页面（客户端处理认证）"""
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/v1/models")
async def list_models():
    import time
    
    current_time = int(time.time())
    
    # 定义所有可用的模型（符合 OpenAI API 标准格式）
    def create_model(model_id: str, owned_by: str = "anthropic"):
        """创建标准格式的模型对象"""
        return {
            "id": model_id,
            "object": "model",
            "created": current_time,
            "owned_by": owned_by,
            "permission": []
        }
    
    models = [
        # 官方支持的 Claude 模型
        create_model("claude-3.5-sonnet"),
        create_model("claude-3.7-sonnet"),
        create_model("claude-4-sonnet"),
    ]
    
    return {
        "object": "list",
        "data": models
    }


@app.get("/health")
async def health():
    """健康检查端点"""
    try:
        db = SessionLocal()
        # 检查数据库连接
        accounts = account_pool_manager.list_accounts(db, active_only=True)
        api_keys = api_key_manager.list_keys(db, active_only=True)
        db.close()
        
        return {
            "status": "healthy",
            "active_accounts": len(accounts),
            "active_api_keys": len(api_keys),
            "version": "2.0.0"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@app.post("/v1/messages")
async def create_message(request: Request, db: Session = Depends(get_db)):
    """
    Claude API 兼容的消息创建端点 (需要API密钥认证)
    """
    # 验证API密钥
    api_key_info = await verify_api_key(request)
    
    try:
        # 解析请求体
        request_data = await request.json()
        logger.info(f"收到 Claude API 请求: {request_data.get('model', 'unknown')}")
        
        # 转换为 ClaudeRequest 对象
        claude_req = parse_claude_request(request_data)
        
        # 从账号池获取可用账号
        account = await account_pool_manager.get_next_account(db)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available accounts in pool"
            )
        
        logger.info(f"使用账号: {account.name}")
        
        # 转换为 CodeWhisperer 请求
        codewhisperer_req = convert_claude_to_codewhisperer_request(
            claude_req,
            conversation_id=None,
            profile_arn=account.profile_arn
        )
        
        # 转换为字典
        codewhisperer_dict = codewhisperer_request_to_dict(codewhisperer_req)
        model = claude_req.model
        
        # 处理历史记录
        conversation_state = codewhisperer_dict.get("conversationState", {})
        history = conversation_state.get("history", [])
        
        if history:
            processed_history = process_claude_history_for_amazonq(history)
            conversation_state["history"] = processed_history
            codewhisperer_dict["conversationState"] = conversation_state
        
        final_request = codewhisperer_dict
        
        # 调试：记录请求的关键信息（用于调试400错误）
        import json
        logger.info(f"请求结构检查: conversationId={codewhisperer_dict.get('conversationState', {}).get('conversationId')}, "
                    f"history_count={len(codewhisperer_dict.get('conversationState', {}).get('history', []))}, "
                    f"has_userInputMessageContext={bool(codewhisperer_dict.get('conversationState', {}).get('currentMessage', {}).get('userInputMessage', {}).get('userInputMessageContext'))}, "
                    f"has_envState={bool(codewhisperer_dict.get('conversationState', {}).get('currentMessage', {}).get('userInputMessage', {}).get('userInputMessageContext', {}).get('envState'))}, "
                    f"modelId={codewhisperer_dict.get('conversationState', {}).get('currentMessage', {}).get('userInputMessage', {}).get('modelId')}")
        # 记录完整请求体（用于调试400错误）
        try:
            request_json = json.dumps(final_request, ensure_ascii=False, indent=2)
            logger.info(f"完整请求体（前2000字符）:\n{request_json[:2000]}...")
        except Exception as e:
            logger.warning(f"无法序列化请求体: {e}")
        
        # 使用账号的token获取认证头
        from auth import refresh_token_for_account
        
        # 为该账号获取token
        try:
            token_data = await refresh_token_for_account(
                account.refresh_token,
                account.client_id,
                account.client_secret
            )
        except Exception as e:
            logger.error(f"账号 {account.name} token 刷新失败: {e}")
            # 标记账号不健康
            account_pool_manager.update_health_status(
                db, account.id, False, f"Token refresh failed: {str(e)}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"账号 {account.name} 认证失败，请检查账号配置（refresh_token、client_id、client_secret）是否正确"
            )
        
        access_token = token_data.get("access_token")
        if not access_token:
            # 标记账号不健康
            account_pool_manager.update_health_status(
                db, account.id, False, "Token refresh returned no access_token"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"账号 {account.name} 无法获取 access_token"
            )
        
        # 构建请求头
        import uuid
        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-amz-json-1.0",
            "X-Amz-Target": "AmazonCodeWhispererStreamingService.GenerateAssistantResponse",
            "User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 md/appVersion-1.19.3 app/AmazonQ-For-CLI",
            "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 m/F app/AmazonQ-For-CLI",
            "X-Amzn-Codewhisperer-Optout": "true",
            "Amz-Sdk-Request": "attempt=1; max=3",
            "Amz-Sdk-Invocation-Id": str(uuid.uuid4()),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br"
        }
        
        # 发送请求到 Amazon Q
        logger.info("正在发送请求到 Amazon Q...")
        
        # API URL
        api_url = os.getenv("AMAZONQ_API_ENDPOINT", "https://q.us-east-1.amazonaws.com/").rstrip('/')
        
        # 创建字节流响应
        async def byte_stream():
            async with httpx.AsyncClient(timeout=300.0) as client:
                try:
                    async with client.stream(
                        "POST",
                        api_url,
                        json=final_request,
                        headers=auth_headers
                    ) as response:
                        if response.status_code != 200:
                            error_text = await response.aread()
                            logger.error(f"上游 API 错误: {response.status_code} {error_text}")
                            # 标记账号不健康
                            account_pool_manager.update_health_status(
                                db, account.id, False, f"API error: {response.status_code}"
                            )
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"上游 API 错误: {error_text.decode()}"
                            )
                        
                        # 处理 Event Stream
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                yield chunk
                
                except httpx.RequestError as e:
                    logger.error(f"请求错误: {e}")
                    account_pool_manager.update_health_status(
                        db, account.id, False, str(e)
                    )
                    raise HTTPException(status_code=502, detail=f"上游服务错误: {str(e)}")
        
        # 返回流式响应
        import json
        import time
        from app.models.database import UsageLog
        
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        last_event_data = None
        
        async def claude_stream():
            nonlocal input_tokens, output_tokens, last_event_data
            try:
                async for event in handle_amazonq_stream(byte_stream(), model=model, request_data=request_data):
                    # 尝试解析事件以获取 tokens 信息
                    if event.startswith("data: "):
                        try:
                            event_data = json.loads(event[6:].strip())
                            if event_data.get("type") == "message_stop" and "usage" in event_data:
                                usage = event_data["usage"]
                                input_tokens = usage.get("input_tokens", 0)
                                output_tokens = usage.get("output_tokens", 0)
                                last_event_data = event_data
                        except (json.JSONDecodeError, KeyError):
                            pass
                    yield event
            finally:
                # 流处理完成后记录使用日志
                try:
                    response_time = time.time() - start_time
                    usage_log = UsageLog(
                        api_key_id=api_key_info.get("api_key_id") if api_key_info else None,
                        account_id=account.id,
                        model=model,
                        endpoint="/v1/messages",
                        method="POST",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        status_code=200,
                        response_time=response_time,
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent")
                    )
                    db.add(usage_log)
                    
                    # 更新账号统计
                    account.total_requests += 1
                    account.total_tokens += (input_tokens + output_tokens)
                    account.last_used = datetime.now()
                    
                    # 注意：API key 统计已在 verify_api_key 的 validate_key 中更新，无需重复更新
                    
                    db.commit()
                except Exception as e:
                    logger.error(f"记录使用日志失败: {e}", exc_info=True)
                    db.rollback()
        
        return StreamingResponse(
            claude_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理请求时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


async def create_message_non_stream(request: Request, db: Session, original_model: str = "gpt-4", api_key_info=None):
    """
    非流式消息创建端点（内部函数）
    收集所有流事件并返回完整响应
    """
    import json
    import time
    from fastapi.responses import JSONResponse
    
    start_time = time.time()
    
    try:
        # 解析请求体
        request_data = await request.json()
        logger.info(f"收到非流式 Claude API 请求: {request_data.get('model', 'unknown')}")
        
        # 转换为 ClaudeRequest 对象
        claude_req = parse_claude_request(request_data)
        
        # 从账号池获取可用账号
        account = await account_pool_manager.get_next_account(db)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available accounts in pool"
            )
        
        logger.info(f"使用账号: {account.name}")
        
        # 转换为 CodeWhisperer 请求
        codewhisperer_req = convert_claude_to_codewhisperer_request(
            claude_req,
            conversation_id=None,
            profile_arn=account.profile_arn
        )
        
        # 转换为字典
        codewhisperer_dict = codewhisperer_request_to_dict(codewhisperer_req)
        model = claude_req.model
        
        # 处理历史记录
        conversation_state = codewhisperer_dict.get("conversationState", {})
        history = conversation_state.get("history", [])
        
        if history:
            processed_history = process_claude_history_for_amazonq(history)
            conversation_state["history"] = processed_history
            codewhisperer_dict["conversationState"] = conversation_state
        
        final_request = codewhisperer_dict
        
        # 调试：记录请求的关键信息（非流式，用于调试400错误）
        import json
        logger.info(f"请求结构检查（非流）: conversationId={codewhisperer_dict.get('conversationState', {}).get('conversationId')}, "
                    f"history_count={len(codewhisperer_dict.get('conversationState', {}).get('history', []))}, "
                    f"has_userInputMessageContext={bool(codewhisperer_dict.get('conversationState', {}).get('currentMessage', {}).get('userInputMessage', {}).get('userInputMessageContext'))}, "
                    f"has_envState={bool(codewhisperer_dict.get('conversationState', {}).get('currentMessage', {}).get('userInputMessage', {}).get('userInputMessageContext', {}).get('envState'))}, "
                    f"modelId={codewhisperer_dict.get('conversationState', {}).get('currentMessage', {}).get('userInputMessage', {}).get('modelId')}")
        # 记录完整请求体（用于调试400错误）
        try:
            request_json = json.dumps(final_request, ensure_ascii=False, indent=2)
            logger.info(f"完整请求体（非流，前2000字符）:\n{request_json[:2000]}...")
        except Exception as e:
            logger.warning(f"无法序列化请求体: {e}")
        
        # 使用账号的token获取认证头
        from auth import refresh_token_for_account
        
        # 为该账号获取token
        try:
            token_data = await refresh_token_for_account(
                account.refresh_token,
                account.client_id,
                account.client_secret
            )
        except Exception as e:
            logger.error(f"账号 {account.name} token 刷新失败: {e}")
            account_pool_manager.update_health_status(
                db, account.id, False, f"Token refresh failed: {str(e)}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"账号 {account.name} 认证失败，请检查账号配置"
            )
        
        access_token = token_data.get("access_token")
        if not access_token:
            account_pool_manager.update_health_status(
                db, account.id, False, "Token refresh returned no access_token"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"账号 {account.name} 无法获取 access_token"
            )
        
        # 构建请求头
        import uuid
        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-amz-json-1.0",
            "X-Amz-Target": "AmazonCodeWhispererStreamingService.GenerateAssistantResponse",
            "User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 md/appVersion-1.19.3 app/AmazonQ-For-CLI",
            "X-Amz-User-Agent": "aws-sdk-rust/1.3.9 ua/2.1 api/codewhispererstreaming/0.1.11582 os/macos lang/rust/1.87.0 m/F app/AmazonQ-For-CLI",
            "X-Amzn-Codewhisperer-Optout": "true",
            "Amz-Sdk-Request": "attempt=1; max=3",
            "Amz-Sdk-Invocation-Id": str(uuid.uuid4()),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br"
        }
        
        # 发送请求到 Amazon Q
        logger.info("正在发送请求到 Amazon Q...")
        api_url = os.getenv("AMAZONQ_API_ENDPOINT", "https://q.us-east-1.amazonaws.com/").rstrip('/')
        
        # 收集所有流事件
        claude_events = []
        
        async def byte_stream():
            async with httpx.AsyncClient(timeout=300.0) as client:
                try:
                    async with client.stream(
                        "POST",
                        api_url,
                        json=final_request,
                        headers=auth_headers
                    ) as response:
                        if response.status_code != 200:
                            error_text = await response.aread()
                            logger.error(f"上游 API 错误: {response.status_code} {error_text}")
                            account_pool_manager.update_health_status(
                                db, account.id, False, f"API error: {response.status_code}"
                            )
                            raise HTTPException(
                                status_code=response.status_code,
                                detail=f"上游 API 错误: {error_text.decode()}"
                            )
                        
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                yield chunk
                
                except httpx.RequestError as e:
                    logger.error(f"请求错误: {e}")
                    account_pool_manager.update_health_status(
                        db, account.id, False, str(e)
                    )
                    raise HTTPException(status_code=502, detail=f"上游服务错误: {str(e)}")
        
        # 收集所有 SSE 事件
        async for sse_event in handle_amazonq_stream(byte_stream(), model=model, request_data=request_data):
            # 解析 SSE 事件（格式: "event: {type}\ndata: {json}\n\n"）
            # 每个 sse_event 是一个完整的 SSE 事件字符串
            lines = sse_event.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        # 流结束
                        break
                    try:
                        event_data = json.loads(data_str)
                        claude_events.append(event_data)
                    except json.JSONDecodeError:
                        continue
        
        # 调试：记录收集到的事件
        logger.debug(f"收集到 {len(claude_events)} 个 Claude 事件")
        for i, event in enumerate(claude_events):
            logger.debug(f"事件 {i}: type={event.get('type')}, keys={list(event.keys())}")
        
        # 转换为 OpenAI 非流格式
        openai_response = convert_claude_to_openai_non_stream(claude_events)
        
        # 调试：记录转换后的响应
        logger.debug(f"转换后的 OpenAI 响应: content={openai_response.get('choices', [{}])[0].get('message', {}).get('content')}")
        
        # 更新模型名称为原始请求的模型
        openai_response["model"] = original_model
        
        # 记录使用日志
        try:
            from app.models.database import UsageLog
            import time
            response_time = time.time() - start_time
            
            # 从响应中提取 tokens
            usage = openai_response.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            
            usage_log = UsageLog(
                api_key_id=api_key_info.get("api_key_id") if api_key_info else None,
                account_id=account.id,
                model=original_model,
                endpoint="/v1/chat/completions",
                method="POST",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                status_code=200,
                response_time=response_time,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent")
            )
            db.add(usage_log)
            
            # 更新账号统计
            account.total_requests += 1
            account.total_tokens += (input_tokens + output_tokens)
            account.last_used = datetime.now()
            
            # 注意：API key 统计已在 verify_api_key 的 validate_key 中更新，无需重复更新
            
            db.commit()
        except Exception as e:
            logger.error(f"记录使用日志失败: {e}", exc_info=True)
            db.rollback()
        
        return JSONResponse(content=openai_response)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理非流请求时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


@app.post("/v1/chat/completions")
async def create_chat_completion(request: Request, db: Session = Depends(get_db)):
    """
    OpenAI API 兼容的聊天完成端点 (需要API密钥认证)
    """
    # 验证API密钥
    api_key_info = await verify_api_key(request)
    
    try:
        # 解析 OpenAI 格式请求
        try:
            body = await request.body()
            if not body:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请求体不能为空"
                )
            openai_request = await request.json()
        except ValueError as e:
            logger.error(f"JSON 解析错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的 JSON 格式: {str(e)}"
            )
        
        logger.info(f"收到 OpenAI API 请求: {openai_request.get('model', 'unknown')}")
        
        # 检查是否为流式请求（默认非流式，除非明确指定 stream: true）
        is_stream = openai_request.get("stream", False)
        
        # 转换为 Claude 格式
        claude_request = convert_openai_to_claude(openai_request)
        
        # 创建新的请求对象，复用 Claude API 处理逻辑
        from fastapi import Request as FastAPIRequest
        
        # 创建一个伪造的请求，包含转换后的 Claude 格式数据
        class FakeRequest:
            def __init__(self, json_data, headers, original_request):
                self._json = json_data
                self.headers = headers
                self.client = original_request.client
                self._original_request = original_request
            
            async def json(self):
                return self._json
        
        fake_request = FakeRequest(claude_request, request.headers, request)
        
        # 如果是非流请求，收集所有事件并返回完整响应
        if not is_stream:
            return await create_message_non_stream(fake_request, db, openai_request.get("model", "gpt-4"), api_key_info)
        
        # 调用 Claude API 处理逻辑（流式）
        return await create_message(fake_request, db)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理 OpenAI 请求时发生错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


def parse_claude_request(data: dict) -> ClaudeRequest:
    """解析 Claude API 请求数据"""
    from models import ClaudeMessage, ClaudeTool
    
    messages = []
    for msg in data.get("messages", []):
        messages.append(ClaudeMessage(
            role=msg["role"],
            content=msg["content"]
        ))
    
    tools = None
    if "tools" in data:
        tools = []
        for tool in data["tools"]:
            tools.append(ClaudeTool(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["input_schema"]
            ))
    
    return ClaudeRequest(
        model=data.get("model", "claude-3.5-sonnet"),
        messages=messages,
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature"),
        tools=tools,
        stream=data.get("stream", True),
        system=data.get("system")
    )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8080"))
    logger.info(f"正在启动服务，监听端口 {port}...")
    uvicorn.run(
        "app_new:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
