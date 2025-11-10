"""
Admin authentication endpoints and dependencies
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.models.database import get_db, AdminUser
from app.core.admin_auth import admin_auth_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def get_session_token(request: Request) -> Optional[str]:
    """Extract session token from cookie"""
    return request.cookies.get("admin_session")


def get_current_admin_user(
    request: Request,
    db: Session = Depends(get_db)
) -> AdminUser:
    """
    Dependency to get current authenticated admin user
    Raises 401 if not authenticated
    """
    session_token = get_session_token(request)
    
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    user = admin_auth_manager.verify_session(db, session_token)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    
    return user


@router.post("/login")
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Admin login endpoint"""
    # Get client info
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    # Authenticate
    session_token = admin_auth_manager.authenticate(
        db=db,
        username=login_data.username,
        password=login_data.password,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Set cookie
    response.set_cookie(
        key="admin_session",
        value=session_token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="lax"
    )
    
    return {"message": "Login successful"}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Admin logout endpoint"""
    session_token = get_session_token(request)
    
    if session_token:
        admin_auth_manager.logout(db, session_token)
    
    # Clear cookie
    response.delete_cookie("admin_session")
    
    return {"message": "Logout successful"}


@router.get("/me")
async def get_current_user_info(
    current_user: AdminUser = Depends(get_current_admin_user)
):
    """Get current user info"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_superuser": current_user.is_superuser,
        "last_login": current_user.last_login,
        "login_count": current_user.login_count
    }


@router.post("/change-password")
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: AdminUser = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Change current user password"""
    success = admin_auth_manager.change_password(
        db=db,
        user_id=current_user.id,
        old_password=password_data.old_password,
        new_password=password_data.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid old password"
        )
    
    return {"message": "Password changed successfully"}
