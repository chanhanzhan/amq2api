"""
Authentication middleware for API key validation
"""
import logging
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.models.database import SessionLocal
from app.core.api_keys import api_key_manager

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def get_api_key_from_request(request: Request) -> Optional[str]:
    """
    Extract API key from request headers
    Supports multiple header formats:
    - Authorization: Bearer <key>
    - x-api-key: <key>
    - api-key: <key>
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
    
    # Try api-key header
    api_key = request.headers.get("api-key")
    if api_key:
        return api_key
    
    return None


async def verify_api_key(request: Request) -> dict:
    """
    Verify API key from request
    Returns API key info if valid, raises HTTPException otherwise
    """
    # Extract API key
    api_key = await get_api_key_from_request(request)
    
    if not api_key:
        logger.warning("No API key provided in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide it via Authorization header (Bearer <key>) or x-api-key header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Validate API key
    db = SessionLocal()
    try:
        api_key_obj = api_key_manager.validate_key(db, api_key)
        
        if not api_key_obj:
            logger.warning(f"Invalid API key: {api_key[:10]}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return {
            "api_key_id": api_key_obj.id,
            "api_key_name": api_key_obj.name,
            "api_key": api_key
        }
    finally:
        db.close()


class ApiKeyMiddleware:
    """Middleware to validate API keys for protected endpoints"""
    
    def __init__(self, app):
        self.app = app
        self.public_paths = ["/", "/health", "/docs", "/redoc", "/openapi.json", "/admin"]
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            
            # Skip authentication for public paths and admin interface
            if any(path.startswith(public_path) for public_path in self.public_paths):
                await self.app(scope, receive, send)
                return
            
            # For API endpoints, require authentication
            if path.startswith("/v1/"):
                request = Request(scope, receive)
                try:
                    api_key_info = await verify_api_key(request)
                    # Store API key info in request state
                    scope["state"] = {"api_key_info": api_key_info}
                except HTTPException as e:
                    # Return error response
                    response = {
                        "error": {
                            "type": "authentication_error",
                            "message": e.detail
                        }
                    }
                    import json
                    body = json.dumps(response).encode()
                    
                    await send({
                        "type": "http.response.start",
                        "status": e.status_code,
                        "headers": [[b"content-type", b"application/json"]],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": body,
                    })
                    return
        
        await self.app(scope, receive, send)
