"""
新的主应用文件
整合账号池管理、API密钥认证、OpenAI API支持和Web管理界面
"""
import logging
import httpx
import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

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
from app.core.openai_converter import convert_openai_to_claude, convert_claude_to_openai_stream
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
    
    logger.info("应用启动完成")
    yield
    
    # 关闭时清理资源
    logger.info("正在关闭服务...")


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
    """根路径重定向到管理界面"""
    return RedirectResponse(url="/admin/dashboard")


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    admin_key = Depends(get_admin_api_key)
):
    """管理面板页面（需要管理员 API 密钥）"""
    return templates.TemplateResponse("admin.html", {"request": request})


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
        
        # 使用账号的token获取认证头
        import asyncio
        from auth import refresh_token as refresh_token_func
        
        # 为该账号获取token
        token_data = await refresh_token_func(
            account.refresh_token,
            account.client_id,
            account.client_secret
        )
        
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get access token for account {account.name}"
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
        async def claude_stream():
            async for event in handle_amazonq_stream(byte_stream(), model=model, request_data=request_data):
                yield event
        
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


@app.post("/v1/chat/completions")
async def create_chat_completion(request: Request, db: Session = Depends(get_db)):
    """
    OpenAI API 兼容的聊天完成端点 (需要API密钥认证)
    """
    # 验证API密钥
    api_key_info = await verify_api_key(request)
    
    try:
        # 解析 OpenAI 格式请求
        openai_request = await request.json()
        logger.info(f"收到 OpenAI API 请求: {openai_request.get('model', 'unknown')}")
        
        # 转换为 Claude 格式
        claude_request = convert_openai_to_claude(openai_request)
        
        # 创建新的请求对象，复用 Claude API 处理逻辑
        from fastapi import Request as FastAPIRequest
        
        # 创建一个伪造的请求，包含转换后的 Claude 格式数据
        class FakeRequest:
            def __init__(self, json_data, headers):
                self._json = json_data
                self.headers = headers
            
            async def json(self):
                return self._json
        
        fake_request = FakeRequest(claude_request, request.headers)
        
        # 调用 Claude API 处理逻辑
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
        model=data.get("model", "claude-sonnet-4.5"),
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
