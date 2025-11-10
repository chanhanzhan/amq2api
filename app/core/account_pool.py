"""
Account pool manager for managing multiple Amazon Q accounts
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.database import Account, get_db

logger = logging.getLogger(__name__)


class AccountPoolManager:
    """Manages a pool of Amazon Q accounts with rotation and health checking"""
    
    def __init__(self):
        self._current_index = 0
        self._lock = asyncio.Lock()
    
    async def get_next_account(self, db: Session) -> Optional[Account]:
        """
        Get next available account from the pool using round-robin
        Returns account with lowest current usage
        """
        async with self._lock:
            # Get all active and healthy accounts
            accounts = db.query(Account).filter(
                and_(
                    Account.is_active == True,
                    Account.is_healthy == True
                )
            ).all()
            
            if not accounts:
                logger.error("No active and healthy accounts available in pool")
                return None
            
            # Find account with lowest current RPM
            best_account = min(accounts, key=lambda a: a.current_rpm)
            
            # Check if account is rate limited
            if best_account.rpm_reset_at and datetime.now() < best_account.rpm_reset_at:
                if best_account.current_rpm >= best_account.requests_per_minute:
                    logger.warning(f"Account {best_account.name} is rate limited")
                    # Try to find another account
                    for account in accounts:
                        if account.id != best_account.id:
                            if not account.rpm_reset_at or datetime.now() >= account.rpm_reset_at:
                                best_account = account
                                break
                            if account.current_rpm < account.requests_per_minute:
                                best_account = account
                                break
            
            # Reset RPM counter if needed
            if not best_account.rpm_reset_at or datetime.now() >= best_account.rpm_reset_at:
                best_account.current_rpm = 0
                best_account.rpm_reset_at = datetime.now() + timedelta(minutes=1)
            
            # Increment usage
            best_account.current_rpm += 1
            best_account.total_requests += 1
            best_account.last_used = datetime.now()
            db.commit()
            
            logger.info(f"Selected account: {best_account.name} (RPM: {best_account.current_rpm}/{best_account.requests_per_minute})")
            return best_account
    
    def add_account(self, db: Session, name: str, refresh_token: str, 
                   client_id: str, client_secret: str, profile_arn: Optional[str] = None,
                   requests_per_minute: int = 10, notes: Optional[str] = None) -> Account:
        """Add a new account to the pool"""
        account = Account(
            name=name,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            profile_arn=profile_arn,
            requests_per_minute=requests_per_minute,
            notes=notes
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        logger.info(f"Added account to pool: {name}")
        return account
    
    def update_account(self, db: Session, account_id: int, **kwargs) -> Optional[Account]:
        """Update account properties"""
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return None
        
        for key, value in kwargs.items():
            if hasattr(account, key):
                setattr(account, key, value)
        
        account.updated_at = datetime.now()
        db.commit()
        db.refresh(account)
        logger.info(f"Updated account: {account.name}")
        return account
    
    def delete_account(self, db: Session, account_id: int) -> bool:
        """Delete account from pool"""
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return False
        
        db.delete(account)
        db.commit()
        logger.info(f"Deleted account: {account.name}")
        return True
    
    def get_account(self, db: Session, account_id: int) -> Optional[Account]:
        """Get account by ID"""
        return db.query(Account).filter(Account.id == account_id).first()
    
    def get_account_by_name(self, db: Session, name: str) -> Optional[Account]:
        """Get account by name"""
        return db.query(Account).filter(Account.name == name).first()
    
    def list_accounts(self, db: Session, active_only: bool = False) -> List[Account]:
        """List all accounts"""
        query = db.query(Account)
        if active_only:
            query = query.filter(Account.is_active == True)
        return query.all()
    
    def update_health_status(self, db: Session, account_id: int, 
                           is_healthy: bool, error_message: Optional[str] = None):
        """Update account health status"""
        account = db.query(Account).filter(Account.id == account_id).first()
        if account:
            account.is_healthy = is_healthy
            account.last_health_check = datetime.now()
            account.health_check_error = error_message
            db.commit()
            logger.info(f"Updated health status for {account.name}: {'healthy' if is_healthy else 'unhealthy'}")
    
    def increment_token_usage(self, db: Session, account_id: int, tokens: int):
        """Increment token usage for account"""
        account = db.query(Account).filter(Account.id == account_id).first()
        if account:
            account.total_tokens += tokens
            db.commit()


# Global instance
account_pool_manager = AccountPoolManager()
