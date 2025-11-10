"""
Admin API endpoints for managing accounts and API keys
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db, Account, ApiKey
from app.core.account_pool import account_pool_manager
from app.core.api_keys import api_key_manager

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
    requests_per_minute: int
    current_rpm: int
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


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    requests_per_minute: Optional[int] = None
    requests_per_day: Optional[int] = None


class ApiKeyResponse(BaseModel):
    id: int
    key: str
    name: str
    description: Optional[str]
    is_active: bool
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
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
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
def list_accounts(active_only: bool = False, db: Session = Depends(get_db)):
    """List all accounts"""
    accounts = account_pool_manager.list_accounts(db, active_only=active_only)
    return accounts


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get account by ID"""
    account = account_pool_manager.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.put("/accounts/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, account_update: AccountUpdate, db: Session = Depends(get_db)):
    """Update account"""
    update_data = account_update.model_dump(exclude_unset=True)
    updated_account = account_pool_manager.update_account(db, account_id, **update_data)
    if not updated_account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return updated_account


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Delete account"""
    success = account_pool_manager.delete_account(db, account_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return {"message": "Account deleted successfully"}


# API Key endpoints
@router.post("/api-keys", response_model=ApiKeyResponse)
def create_api_key(api_key: ApiKeyCreate, db: Session = Depends(get_db)):
    """Create a new API key"""
    try:
        new_key = api_key_manager.create_key(
            db=db,
            name=api_key.name,
            description=api_key.description,
            requests_per_minute=api_key.requests_per_minute,
            requests_per_day=api_key.requests_per_day,
            expires_days=api_key.expires_days
        )
        return new_key
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/api-keys", response_model=List[ApiKeyResponse])
def list_api_keys(active_only: bool = False, db: Session = Depends(get_db)):
    """List all API keys"""
    keys = api_key_manager.list_keys(db, active_only=active_only)
    return keys


@router.get("/api-keys/{key_id}", response_model=ApiKeyResponse)
def get_api_key(key_id: int, db: Session = Depends(get_db)):
    """Get API key by ID"""
    api_key = api_key_manager.get_key(db, key_id)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return api_key


@router.put("/api-keys/{key_id}", response_model=ApiKeyResponse)
def update_api_key(key_id: int, api_key_update: ApiKeyUpdate, db: Session = Depends(get_db)):
    """Update API key"""
    update_data = api_key_update.model_dump(exclude_unset=True)
    updated_key = api_key_manager.update_key(db, key_id, **update_data)
    if not updated_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return updated_key


@router.delete("/api-keys/{key_id}")
def delete_api_key(key_id: int, db: Session = Depends(get_db)):
    """Delete API key"""
    success = api_key_manager.delete_key(db, key_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"message": "API key deleted successfully"}


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: int, db: Session = Depends(get_db)):
    """Revoke (deactivate) an API key"""
    success = api_key_manager.revoke_key(db, key_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"message": "API key revoked successfully"}


# Statistics endpoints
@router.get("/stats/accounts")
def get_account_stats(db: Session = Depends(get_db)):
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
def get_api_key_stats(db: Session = Depends(get_db)):
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
