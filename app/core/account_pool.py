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
            # 检查并自动恢复账号（错误后30分钟自动恢复）
            self._check_and_auto_recover_accounts(db)
            
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
    
    def _check_and_auto_recover_accounts(self, db: Session):
        """检查并自动恢复账号（错误后30分钟自动恢复）"""
        now = datetime.now()
        # 查找需要自动恢复的账号（错误后30分钟）
        accounts_to_recover = db.query(Account).filter(
            and_(
                Account.is_healthy == False,
                Account.auto_recover_at != None,
                Account.auto_recover_at <= now
            )
        ).all()
        
        for account in accounts_to_recover:
            account.is_healthy = True
            account.error_count = 0
            account.first_error_time = None
            account.last_error_time = None
            account.health_check_error = None
            account.auto_recover_at = None
            account.last_health_check = now
            logger.info(f"账号 {account.name} 自动恢复健康状态（错误后30分钟）")
        
        if accounts_to_recover:
            db.commit()
    
    def _cleanup_old_errors(self, account: Account, now: datetime, error_window_minutes: int = 10):
        """
        清理超过时间窗口的错误计数
        只统计最近 error_window_minutes 分钟内的错误
        """
        if not account.first_error_time:
            return
        
        # 计算时间窗口
        window_start = now - timedelta(minutes=error_window_minutes)
        
        # 如果第一次错误时间超过窗口，重置计数
        if account.first_error_time < window_start:
            account.error_count = 0
            account.first_error_time = None
            account.last_error_time = None
            logger.debug(f"账号 {account.name} 错误计数已过期，已重置")
    
    def update_health_status(self, db: Session, account_id: int, 
                           is_healthy: bool, error_message: Optional[str] = None,
                           error_window_minutes: int = 10):
        """
        Update account health status with time-window based error counting
        - 只统计最近 error_window_minutes 分钟内的错误
        - 错误5次以上才标记为异常
        - 错误后30分钟自动恢复
        """
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return
        
        now = datetime.now()
        
        if is_healthy:
            # 成功请求：重置错误计数
            if account.error_count > 0:
                account.error_count = 0
                account.first_error_time = None
                account.last_error_time = None
                account.health_check_error = None
                account.auto_recover_at = None
                if not account.is_healthy:
                    account.is_healthy = True
                    logger.info(f"账号 {account.name} 恢复健康状态（成功请求）")
        else:
            # 清理超过时间窗口的旧错误
            self._cleanup_old_errors(account, now, error_window_minutes)
            
            # 检查是否在时间窗口内
            window_start = now - timedelta(minutes=error_window_minutes)
            
            # 如果这是时间窗口内的第一次错误，设置 first_error_time
            if not account.first_error_time or account.first_error_time < window_start:
                account.first_error_time = now
                account.error_count = 1
            else:
                # 在时间窗口内，增加错误计数
                account.error_count = (account.error_count or 0) + 1
            
            account.last_error_time = now
            account.last_health_check = now
            account.health_check_error = error_message
            
            # 错误5次以上才标记为异常
            if account.error_count >= 5:
                if account.is_healthy:
                    account.is_healthy = False
                    # 设置30分钟后自动恢复
                    account.auto_recover_at = now + timedelta(minutes=30)
                    logger.warning(f"账号 {account.name} 标记为异常（最近{error_window_minutes}分钟内错误 {account.error_count} 次）")
                else:
                    # 如果已经是异常状态，更新自动恢复时间
                    if not account.auto_recover_at or account.auto_recover_at < now:
                        account.auto_recover_at = now + timedelta(minutes=30)
            else:
                logger.info(f"账号 {account.name} 错误计数: {account.error_count}/5（最近{error_window_minutes}分钟内，未达到异常阈值）")
        
        db.commit()
    
    def record_success(self, db: Session, account_id: int):
        """记录成功请求，重置错误计数"""
        account = db.query(Account).filter(Account.id == account_id).first()
        if account and account.error_count > 0:
            account.error_count = 0
            account.first_error_time = None
            account.last_error_time = None
            account.health_check_error = None
            account.auto_recover_at = None
            if not account.is_healthy:
                account.is_healthy = True
                logger.info(f"账号 {account.name} 恢复健康状态（成功请求）")
            db.commit()
    
    def increment_token_usage(self, db: Session, account_id: int, tokens: int):
        """Increment token usage for account"""
        account = db.query(Account).filter(Account.id == account_id).first()
        if account:
            account.total_tokens += tokens
            db.commit()


# Global instance
account_pool_manager = AccountPoolManager()
