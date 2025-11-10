"""
Admin API endpoints for managing accounts and API keys
"""
import logging
import json
import asyncio
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db, Account, ApiKey
from app.core.account_pool import account_pool_manager
from app.core.api_keys import api_key_manager
from app.core.admin_api_auth import get_admin_api_key
from auth import refresh_token_for_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# Pydantic models for requests/responses
class AccountCreate(BaseModel):
    name: str
    refresh_token: str
    client_id: str
    client_secret: str
    profile_arn: Optional[str] = None
    requests_per_minute: int = 10
    notes: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    profile_arn: Optional[str] = None
    is_active: Optional[bool] = None
    requests_per_minute: Optional[int] = None
    notes: Optional[str] = None


class AccountResponse(BaseModel):
    id: int
    name: str
    profile_arn: Optional[str]
    is_active: bool
    is_healthy: bool
    total_requests: int
    total_tokens: int
    last_used: Optional[datetime]
    last_health_check: Optional[datetime]
    health_check_error: Optional[str]
    error_count: Optional[int] = 0
    last_error_time: Optional[datetime] = None
    first_error_time: Optional[datetime] = None
    auto_recover_at: Optional[datetime] = None
    requests_per_minute: int
    current_rpm: int
    rpm_reset_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    notes: Optional[str]

    class Config:
        from_attributes = True


class ApiKeyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    requests_per_minute: int = 60
    requests_per_day: int = 10000
    expires_days: Optional[int] = None
    is_admin: bool = False  # Add admin flag


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None  # Add admin flag
    requests_per_minute: Optional[int] = None
    requests_per_day: Optional[int] = None


class ApiKeyResponse(BaseModel):
    id: int
    key: str
    name: str
    description: Optional[str]
    is_active: bool
    is_admin: bool  # Add admin flag
    total_requests: int
    last_used: Optional[datetime]
    requests_per_minute: int
    requests_per_day: int
    current_rpm: int
    current_rpd: int
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]

    class Config:
        from_attributes = True


# Account endpoints
@router.post("/accounts", response_model=AccountResponse)
def create_account(
    account: AccountCreate, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Create a new account in the pool"""
    try:
        new_account = account_pool_manager.add_account(
            db=db,
            name=account.name,
            refresh_token=account.refresh_token,
            client_id=account.client_id,
            client_secret=account.client_secret,
            profile_arn=account.profile_arn,
            requests_per_minute=account.requests_per_minute,
            notes=account.notes
        )
        return new_account
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/accounts", response_model=List[AccountResponse])
def list_accounts(
    active_only: bool = False, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """List all accounts"""
    accounts = account_pool_manager.list_accounts(db, active_only=active_only)
    return accounts


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Get account by ID"""
    account = account_pool_manager.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.put("/accounts/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int, 
    account_update: AccountUpdate, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Update account"""
    update_data = account_update.model_dump(exclude_unset=True)
    updated_account = account_pool_manager.update_account(db, account_id, **update_data)
    if not updated_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return updated_account


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: int, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Delete account"""
    success = account_pool_manager.delete_account(db, account_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return {"message": "Account deleted successfully"}


# API Key endpoints
@router.post("/api-keys", response_model=ApiKeyResponse)
def create_api_key(
    api_key: ApiKeyCreate, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Create a new API key"""
    try:
        new_key = api_key_manager.create_key(
            db=db,
            name=api_key.name,
            description=api_key.description,
            requests_per_minute=api_key.requests_per_minute,
            requests_per_day=api_key.requests_per_day,
            expires_days=api_key.expires_days,
            is_admin=api_key.is_admin
        )
        return new_key
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/api-keys", response_model=List[ApiKeyResponse])
def list_api_keys(
    active_only: bool = False, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """List all API keys"""
    keys = api_key_manager.list_keys(db, active_only=active_only)
    return keys


@router.get("/api-keys/{key_id}", response_model=ApiKeyResponse)
def get_api_key(
    key_id: int, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Get API key by ID"""
    api_key = api_key_manager.get_key(db, key_id)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return api_key


@router.put("/api-keys/{key_id}", response_model=ApiKeyResponse)
def update_api_key(
    key_id: int, 
    api_key_update: ApiKeyUpdate, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Update API key"""
    update_data = api_key_update.model_dump(exclude_unset=True)
    updated_key = api_key_manager.update_key(db, key_id, **update_data)
    if not updated_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return updated_key


@router.delete("/api-keys/{key_id}")
def delete_api_key(
    key_id: int, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Delete API key"""
    success = api_key_manager.delete_key(db, key_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"message": "API key deleted successfully"}


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(
    key_id: int, 
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Revoke (deactivate) an API key"""
    success = api_key_manager.revoke_key(db, key_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"message": "API key revoked successfully"}


# Statistics endpoints
@router.get("/stats/accounts")
def get_account_stats(
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Get account statistics"""
    accounts = db.query(Account).all()
    total_accounts = len(accounts)
    active_accounts = len([a for a in accounts if a.is_active])
    healthy_accounts = len([a for a in accounts if a.is_healthy])
    total_requests = sum(a.total_requests for a in accounts)
    total_tokens = sum(a.total_tokens for a in accounts)
    
    return {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "healthy_accounts": healthy_accounts,
        "total_requests": total_requests,
        "total_tokens": total_tokens
    }


@router.get("/stats/api-keys")
def get_api_key_stats(
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Get API key statistics"""
    api_keys = db.query(ApiKey).all()
    total_keys = len(api_keys)
    active_keys = len([k for k in api_keys if k.is_active])
    total_requests = sum(k.total_requests for k in api_keys)
    
    return {
        "total_keys": total_keys,
        "active_keys": active_keys,
        "total_requests": total_requests
    }


@router.get("/stats/tokens")
def get_tokens_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Get tokens usage statistics"""
    from datetime import datetime, timedelta
    from app.models.database import UsageLog
    from sqlalchemy import func
    
    # 计算时间范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 查询指定时间范围内的 tokens 使用情况
    stats = db.query(
        func.sum(UsageLog.input_tokens).label('total_input_tokens'),
        func.sum(UsageLog.output_tokens).label('total_output_tokens'),
        func.count(UsageLog.id).label('total_requests')
    ).filter(
        UsageLog.timestamp >= start_date,
        UsageLog.timestamp <= end_date
    ).first()
    
    # 按日期分组统计
    daily_stats = db.query(
        func.date(UsageLog.timestamp).label('date'),
        func.sum(UsageLog.input_tokens).label('input_tokens'),
        func.sum(UsageLog.output_tokens).label('output_tokens'),
        func.count(UsageLog.id).label('requests')
    ).filter(
        UsageLog.timestamp >= start_date,
        UsageLog.timestamp <= end_date
    ).group_by(
        func.date(UsageLog.timestamp)
    ).order_by(
        func.date(UsageLog.timestamp)
    ).all()
    
    # 按账号分组统计
    account_stats = db.query(
        UsageLog.account_id,
        Account.name,
        func.sum(UsageLog.input_tokens).label('input_tokens'),
        func.sum(UsageLog.output_tokens).label('output_tokens'),
        func.count(UsageLog.id).label('requests')
    ).join(
        Account, UsageLog.account_id == Account.id
    ).filter(
        UsageLog.timestamp >= start_date,
        UsageLog.timestamp <= end_date
    ).group_by(
        UsageLog.account_id, Account.name
    ).order_by(
        func.sum(UsageLog.input_tokens + UsageLog.output_tokens).desc()
    ).all()
    
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": days
        },
        "total": {
            "input_tokens": int(stats.total_input_tokens or 0),
            "output_tokens": int(stats.total_output_tokens or 0),
            "total_tokens": int((stats.total_input_tokens or 0) + (stats.total_output_tokens or 0)),
            "requests": int(stats.total_requests or 0)
        },
        "daily": [
            {
                "date": stat.date.isoformat() if hasattr(stat.date, 'isoformat') else str(stat.date),
                "input_tokens": int(stat.input_tokens or 0),
                "output_tokens": int(stat.output_tokens or 0),
                "total_tokens": int((stat.input_tokens or 0) + (stat.output_tokens or 0)),
                "requests": int(stat.requests or 0)
            }
            for stat in daily_stats
        ],
        "by_account": [
            {
                "account_id": stat.account_id,
                "account_name": stat.name,
                "input_tokens": int(stat.input_tokens or 0),
                "output_tokens": int(stat.output_tokens or 0),
                "total_tokens": int((stat.input_tokens or 0) + (stat.output_tokens or 0)),
                "requests": int(stat.requests or 0)
            }
            for stat in account_stats
        ]
    }


@router.get("/stats/account-usage")
def get_account_usage_stats(
    days: int = 7,
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """Get account usage statistics"""
    from datetime import datetime, timedelta
    from app.models.database import UsageLog
    from sqlalchemy import func
    
    # 计算时间范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 获取所有账号及其使用统计
    accounts = db.query(Account).all()
    
    account_usage = []
    for account in accounts:
        # 查询该账号在指定时间范围内的使用情况
        usage = db.query(
            func.sum(UsageLog.input_tokens).label('input_tokens'),
            func.sum(UsageLog.output_tokens).label('output_tokens'),
            func.count(UsageLog.id).label('requests')
        ).filter(
            UsageLog.account_id == account.id,
            UsageLog.timestamp >= start_date,
            UsageLog.timestamp <= end_date
        ).first()
        
        account_usage.append({
            "account_id": account.id,
            "account_name": account.name,
            "is_active": account.is_active,
            "is_healthy": account.is_healthy,
            "input_tokens": int(usage.input_tokens or 0),
            "output_tokens": int(usage.output_tokens or 0),
            "total_tokens": int((usage.input_tokens or 0) + (usage.output_tokens or 0)),
            "requests": int(usage.requests or 0),
            "total_requests_all_time": account.total_requests,
            "total_tokens_all_time": account.total_tokens,
            "last_used": account.last_used.isoformat() if account.last_used else None
        })
    
    # 按总 tokens 排序
    account_usage.sort(key=lambda x: x["total_tokens"], reverse=True)
    
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": days
        },
        "accounts": account_usage
    }


@router.post("/accounts/{account_id}/refresh-token")
def refresh_account_token(
    account_id: int,
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """主动刷新账号的 token"""
    import asyncio
    from auth import refresh_token_for_account
    from app.core.redis_cache import delete_token_cache
    
    account = account_pool_manager.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    try:
        # 删除旧的缓存
        delete_token_cache(str(account_id))
        
        # 刷新 token
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            token_data = loop.run_until_complete(
                refresh_token_for_account(
                    account.refresh_token,
                    account.client_id,
                    account.client_secret,
                    account_id=str(account_id)
                )
            )
        finally:
            loop.close()
        
        # 更新账号健康状态
        account_pool_manager.update_health_status(db, account_id, True, None)
        
        return {
            "message": "Token refreshed successfully",
            "account_id": account_id,
            "account_name": account.name,
            "expires_in": token_data.get("expires_in")
        }
    except Exception as e:
        logger.error(f"刷新账号 {account_id} token 失败: {e}")
        account_pool_manager.update_health_status(db, account_id, False, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}"
        )


@router.get("/accounts/{account_id}/stats")
def get_account_detailed_stats(
    account_id: int,
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """获取账号详细统计信息"""
    account = account_pool_manager.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    from datetime import datetime
    from app.core.redis_cache import get_token_cache
    
    # 检查 Redis 中的 token 缓存
    token_cache = get_token_cache(str(account_id))
    token_info = None
    if token_cache:
        expires_at = datetime.fromisoformat(token_cache['expires_at'])
        token_info = {
            "cached": True,
            "expires_at": expires_at.isoformat(),
            "is_valid": datetime.now() < expires_at
        }
    else:
        token_info = {
            "cached": False,
            "expires_at": None,
            "is_valid": False
        }
    
    return {
        "account_id": account.id,
        "account_name": account.name,
        "is_active": account.is_active,
        "is_healthy": account.is_healthy,
        "error_count": account.error_count or 0,
        "last_error_time": account.last_error_time.isoformat() if account.last_error_time else None,
        "last_health_check": account.last_health_check.isoformat() if account.last_health_check else None,
        "health_check_error": account.health_check_error,
        "auto_recover_at": account.auto_recover_at.isoformat() if account.auto_recover_at else None,
        "total_requests": account.total_requests,
        "total_tokens": account.total_tokens,
        "last_used": account.last_used.isoformat() if account.last_used else None,
        "requests_per_minute": account.requests_per_minute,
        "current_rpm": account.current_rpm,
        "rpm_reset_at": account.rpm_reset_at.isoformat() if account.rpm_reset_at else None,
        "token_info": token_info,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat()
    }


@router.post("/accounts/upload-json")
async def upload_json_and_create_account(
    json_file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    profile_arn: Optional[str] = Form(None),
    requests_per_minute: int = Form(10),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin_key: ApiKey = Depends(get_admin_api_key)
):
    """
    上传 AWS SSO JSON 文件，自动提取配置并创建账号，然后立即刷新 token
    """
    try:
        # 读取文件内容
        content = await json_file.read()
        
        # 解析 JSON
        try:
            data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的 JSON 格式: {str(e)}"
            )
        
        # 提取字段
        client_id = data.get("clientId")
        refresh_token = data.get("refreshToken")
        client_secret = data.get("clientSecret")
        region = data.get("region")
        
        # 验证必需字段
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON 文件中缺少 clientId 字段"
            )
        
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON 文件中缺少 refreshToken 字段"
            )
        
        if not client_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON 文件中缺少 clientSecret 字段"
            )
        
        # 检查是否已存在相同 client_id 的账号
        existing_account = db.query(Account).filter(Account.client_id == client_id).first()
        if existing_account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"账号已存在: {existing_account.name} (ID: {existing_account.id})"
            )
        
        # 如果没有提供名称，自动生成
        if not name:
            from datetime import datetime
            name = f"AWS-SSO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # 使用 region 作为 profile_arn（如果没有提供）
        if not profile_arn:
            profile_arn = region
        
        # 创建备注
        if not notes:
            notes = f"从 JSON 文件自动添加 (文件: {json_file.filename})"
        
        # 添加到账号池
        account = account_pool_manager.add_account(
            db=db,
            name=name,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            profile_arn=profile_arn,
            requests_per_minute=requests_per_minute,
            notes=notes
        )
        
        logger.info(f"从 JSON 文件添加账号: {account.name} (ID: {account.id})")
        
        # 立即刷新 token
        try:
            from app.core.redis_cache import delete_token_cache
            # 删除旧的缓存（如果有）
            delete_token_cache(str(account.id))
            
            # 刷新 token
            token_data = await refresh_token_for_account(
                account.refresh_token,
                account.client_id,
                account.client_secret,
                account_id=str(account.id)
            )
            
            # 更新账号健康状态
            account_pool_manager.update_health_status(db, account.id, True, None)
            
            logger.info(f"账号 {account.name} token 刷新成功")
            
            return JSONResponse(content={
                "success": True,
                "message": f"账号 {account.name} 已成功添加并刷新 Token",
                "account": {
                    "id": account.id,
                    "name": account.name,
                    "client_id": account.client_id,
                    "profile_arn": account.profile_arn,
                    "is_active": account.is_active,
                    "is_healthy": account.is_healthy,
                    "created_at": account.created_at.isoformat()
                },
                "token_refresh": {
                    "success": True,
                    "expires_in": token_data.get("expires_in")
                }
            })
        
        except Exception as e:
            logger.error(f"账号 {account.name} token 刷新失败: {e}")
            account_pool_manager.update_health_status(db, account.id, False, f"Token refresh failed: {str(e)}")
            
            # 即使 token 刷新失败，也返回账号创建成功的信息
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "success": True,
                    "message": f"账号 {account.name} 已成功添加，但 Token 刷新失败",
                    "account": {
                        "id": account.id,
                        "name": account.name,
                        "client_id": account.client_id,
                        "profile_arn": account.profile_arn,
                        "is_active": account.is_active,
                        "is_healthy": account.is_healthy,
                        "created_at": account.created_at.isoformat()
                    },
                    "token_refresh": {
                        "success": False,
                        "error": str(e)
                    },
                    "warning": "请手动刷新 Token"
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传 JSON 并创建账号时发生错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部服务器错误: {str(e)}"
        )
