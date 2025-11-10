"""
Admin authentication using API keys
"""
import logging
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.models.database import get_db, ApiKey
from app.core.api_keys import api_key_manager

logger = logging.getLogger(__name__)


async def get_api_key_from_header(request: Request) -> Optional[str]:
    """
    Extract API key from request headers
    Supports multiple header formats:
    - Authorization: Bearer <key>
    - x-api-key: <key>
    """
    # Try Authorization header (Bearer token)
    auth_header = request.headers.get("Authorization")
    if auth_header:
        if auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
    
    # Try x-api-key header
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key
    
    return None


async def get_current_api_key(
    request: Request,
    db: Session = Depends(get_db)
) -> ApiKey:
    """
    Dependency to get current API key
    Raises 401 if not authenticated
    """
    api_key_str = await get_api_key_from_header(request)
    
    if not api_key_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide it via Authorization header (Bearer <key>) or x-api-key header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Validate API key
    api_key_obj = api_key_manager.validate_key(db, api_key_str)
    
    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return api_key_obj


async def get_admin_api_key(
    api_key: ApiKey = Depends(get_current_api_key)
) -> ApiKey:
    """
    Dependency to ensure current API key has admin privileges
    Raises 403 if not an admin key
    """
    if not api_key.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required. Use an API key with admin flag set to true."
        )
    
    return api_key
