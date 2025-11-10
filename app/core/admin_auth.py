"""
Admin authentication manager for web interface
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models.database import AdminUser, AdminSession

logger = logging.getLogger(__name__)

# Session configuration
SESSION_EXPIRY_HOURS = 24
SESSION_INACTIVITY_MINUTES = 120


class AdminAuthManager:
    """Manages admin authentication for web interface"""
    
    def authenticate(self, db: Session, username: str, password: str, 
                    ip_address: str = None, user_agent: str = None) -> Optional[str]:
        """
        Authenticate admin user and create session
        Returns session token if successful, None otherwise
        """
        # Find user
        user = db.query(AdminUser).filter(
            AdminUser.username == username,
            AdminUser.is_active == True
        ).first()
        
        if not user:
            logger.warning(f"Login failed: user '{username}' not found")
            return None
        
        # Verify password
        if not user.verify_password(password):
            logger.warning(f"Login failed: invalid password for user '{username}'")
            return None
        
        # Update login info
        user.last_login = datetime.now()
        user.login_count += 1
        
        # Create session token
        session_token = secrets.token_urlsafe(48)
        expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRY_HOURS)
        
        session = AdminSession(
            session_token=session_token,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        
        db.add(session)
        db.commit()
        
        logger.info(f"User '{username}' logged in successfully")
        return session_token
    
    def verify_session(self, db: Session, session_token: str) -> Optional[AdminUser]:
        """
        Verify session token and return user if valid
        """
        if not session_token:
            return None
        
        # Find session
        session = db.query(AdminSession).filter(
            AdminSession.session_token == session_token
        ).first()
        
        if not session:
            return None
        
        # Check expiration
        now = datetime.now()
        if now > session.expires_at:
            logger.info(f"Session expired for token {session_token[:10]}...")
            db.delete(session)
            db.commit()
            return None
        
        # Check inactivity timeout
        inactivity_limit = now - timedelta(minutes=SESSION_INACTIVITY_MINUTES)
        if session.last_activity < inactivity_limit:
            logger.info(f"Session inactive for token {session_token[:10]}...")
            db.delete(session)
            db.commit()
            return None
        
        # Update last activity
        session.last_activity = now
        db.commit()
        
        # Get user
        user = db.query(AdminUser).filter(
            AdminUser.id == session.user_id,
            AdminUser.is_active == True
        ).first()
        
        return user
    
    def logout(self, db: Session, session_token: str) -> bool:
        """
        Logout (delete session)
        """
        session = db.query(AdminSession).filter(
            AdminSession.session_token == session_token
        ).first()
        
        if session:
            db.delete(session)
            db.commit()
            logger.info(f"Session logged out: {session_token[:10]}...")
            return True
        
        return False
    
    def create_user(self, db: Session, username: str, password: str,
                   email: str = None, full_name: str = None,
                   is_superuser: bool = False) -> AdminUser:
        """
        Create a new admin user
        """
        # Check if user exists
        existing = db.query(AdminUser).filter(AdminUser.username == username).first()
        if existing:
            raise ValueError(f"User '{username}' already exists")
        
        # Hash password
        password_hash, salt = AdminUser.hash_password(password)
        
        # Create user
        user = AdminUser(
            username=username,
            password_hash=password_hash,
            salt=salt,
            email=email,
            full_name=full_name,
            is_superuser=is_superuser
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logger.info(f"Created admin user: {username}")
        return user
    
    def change_password(self, db: Session, user_id: int, 
                       old_password: str, new_password: str) -> bool:
        """
        Change user password
        """
        user = db.query(AdminUser).filter(AdminUser.id == user_id).first()
        if not user:
            return False
        
        # Verify old password
        if not user.verify_password(old_password):
            logger.warning(f"Password change failed: invalid old password for user {user.username}")
            return False
        
        # Update password
        password_hash, salt = AdminUser.hash_password(new_password)
        user.password_hash = password_hash
        user.salt = salt
        user.updated_at = datetime.now()
        
        # Invalidate all sessions for this user
        db.query(AdminSession).filter(AdminSession.user_id == user_id).delete()
        
        db.commit()
        logger.info(f"Password changed for user: {user.username}")
        return True
    
    def cleanup_expired_sessions(self, db: Session) -> int:
        """
        Clean up expired sessions
        Returns number of sessions deleted
        """
        now = datetime.now()
        count = db.query(AdminSession).filter(
            AdminSession.expires_at < now
        ).delete()
        db.commit()
        
        if count > 0:
            logger.info(f"Cleaned up {count} expired sessions")
        
        return count


# Global instance
admin_auth_manager = AdminAuthManager()
