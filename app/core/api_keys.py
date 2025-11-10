"""
API Key management for authentication
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.database import ApiKey

logger = logging.getLogger(__name__)


class ApiKeyManager:
    """Manages API keys for authentication"""
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new random API key"""
        return f"amq-{secrets.token_urlsafe(32)}"
    
    def create_key(self, db: Session, name: str, description: Optional[str] = None,
                  requests_per_minute: int = 60, requests_per_day: int = 10000,
                  expires_days: Optional[int] = None) -> ApiKey:
        """Create a new API key"""
        key = self.generate_key()
        expires_at = None
        if expires_days:
            expires_at = datetime.now() + timedelta(days=expires_days)
        
        api_key = ApiKey(
            key=key,
            name=name,
            description=description,
            requests_per_minute=requests_per_minute,
            requests_per_day=requests_per_day,
            expires_at=expires_at
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        logger.info(f"Created new API key: {name}")
        return api_key
    
    def validate_key(self, db: Session, key: str) -> Optional[ApiKey]:
        """
        Validate an API key
        Returns the API key object if valid, None otherwise
        """
        api_key = db.query(ApiKey).filter(ApiKey.key == key).first()
        
        if not api_key:
            return None
        
        # Check if active
        if not api_key.is_active:
            logger.warning(f"API key {api_key.name} is inactive")
            return None
        
        # Check expiration
        if api_key.expires_at and datetime.now() > api_key.expires_at:
            logger.warning(f"API key {api_key.name} has expired")
            return None
        
        # Check rate limits
        if api_key.rpm_reset_at and datetime.now() < api_key.rpm_reset_at:
            if api_key.current_rpm >= api_key.requests_per_minute:
                logger.warning(f"API key {api_key.name} exceeded RPM limit")
                return None
        else:
            # Reset RPM counter
            api_key.current_rpm = 0
            api_key.rpm_reset_at = datetime.now() + timedelta(minutes=1)
        
        if api_key.rpd_reset_at and datetime.now() < api_key.rpd_reset_at:
            if api_key.current_rpd >= api_key.requests_per_day:
                logger.warning(f"API key {api_key.name} exceeded RPD limit")
                return None
        else:
            # Reset RPD counter
            api_key.current_rpd = 0
            api_key.rpd_reset_at = datetime.now() + timedelta(days=1)
        
        # Increment counters
        api_key.current_rpm += 1
        api_key.current_rpd += 1
        api_key.total_requests += 1
        api_key.last_used = datetime.now()
        db.commit()
        
        return api_key
    
    def get_key(self, db: Session, key_id: int) -> Optional[ApiKey]:
        """Get API key by ID"""
        return db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    def list_keys(self, db: Session, active_only: bool = False) -> List[ApiKey]:
        """List all API keys"""
        query = db.query(ApiKey)
        if active_only:
            query = query.filter(ApiKey.is_active == True)
        return query.all()
    
    def update_key(self, db: Session, key_id: int, **kwargs) -> Optional[ApiKey]:
        """Update API key properties"""
        api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not api_key:
            return None
        
        for key, value in kwargs.items():
            if hasattr(api_key, key) and key != 'key':  # Don't allow changing the key itself
                setattr(api_key, key, value)
        
        api_key.updated_at = datetime.now()
        db.commit()
        db.refresh(api_key)
        logger.info(f"Updated API key: {api_key.name}")
        return api_key
    
    def delete_key(self, db: Session, key_id: int) -> bool:
        """Delete API key"""
        api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not api_key:
            return False
        
        db.delete(api_key)
        db.commit()
        logger.info(f"Deleted API key: {api_key.name}")
        return True
    
    def revoke_key(self, db: Session, key_id: int) -> bool:
        """Revoke (deactivate) an API key"""
        api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not api_key:
            return False
        
        api_key.is_active = False
        api_key.updated_at = datetime.now()
        db.commit()
        logger.info(f"Revoked API key: {api_key.name}")
        return True


# Global instance
api_key_manager = ApiKeyManager()
