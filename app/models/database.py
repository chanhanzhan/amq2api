"""
Database models for account pool and API keys
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import hashlib
import secrets

Base = declarative_base()


class Account(Base):
    """Amazon Q account in the pool"""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    refresh_token = Column(Text, nullable=False)
    client_id = Column(String(200), nullable=False)
    client_secret = Column(String(200), nullable=False)
    profile_arn = Column(String(500), nullable=True)
    
    # Status and health
    is_active = Column(Boolean, default=True)
    is_healthy = Column(Boolean, default=True)
    last_health_check = Column(DateTime, nullable=True)
    health_check_error = Column(Text, nullable=True)
    
    # Usage statistics
    total_requests = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    last_used = Column(DateTime, nullable=True)
    
    # Rate limiting
    requests_per_minute = Column(Integer, default=10)
    current_rpm = Column(Integer, default=0)
    rpm_reset_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    notes = Column(Text, nullable=True)


class ApiKey(Base):
    """API keys for authentication"""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # Admin privilege for web interface
    
    # Usage statistics
    total_requests = Column(Integer, default=0)
    last_used = Column(DateTime, nullable=True)
    
    # Rate limiting (per key)
    requests_per_minute = Column(Integer, default=60)
    requests_per_day = Column(Integer, default=10000)
    current_rpm = Column(Integer, default=0)
    current_rpd = Column(Integer, default=0)
    rpm_reset_at = Column(DateTime, nullable=True)
    rpd_reset_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    expires_at = Column(DateTime, nullable=True)


class AdminUser(Base):
    """Admin users for web interface authentication"""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    salt = Column(String(32), nullable=False)
    
    # User info
    email = Column(String(100), nullable=True)
    full_name = Column(String(100), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    
    # Session management
    last_login = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple:
        """Hash password with salt"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        
        return password_hash, salt
    
    def verify_password(self, password: str) -> bool:
        """Verify password"""
        password_hash, _ = self.hash_password(password, self.salt)
        return password_hash == self.password_hash


class AdminSession(Base):
    """Admin session tokens"""
    __tablename__ = "admin_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_token = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    
    # Session info
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Expiration
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.now)


class UsageLog(Base):
    """Usage logs for tracking requests"""
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_id = Column(Integer, nullable=True)
    account_id = Column(Integer, nullable=True)
    
    # Request info
    model = Column(String(100))
    endpoint = Column(String(200))
    method = Column(String(10))
    
    # Token usage
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    
    # Response info
    status_code = Column(Integer)
    response_time = Column(Float)  # in seconds
    error_message = Column(Text, nullable=True)
    
    # Metadata
    timestamp = Column(DateTime, default=datetime.now)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)


# Database setup
DB_PATH = os.getenv("DATABASE_PATH", "data/amq2api.db")
os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else "data", exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    
    # Create default admin API key if none exists
    db = SessionLocal()
    try:
        admin_key_count = db.query(ApiKey).filter(ApiKey.is_admin == True).count()
        if admin_key_count == 0:
            # Create default admin API key
            default_key = "amq-admin-default-key-change-immediately"
            default_admin_key = ApiKey(
                key=default_key,
                name="默认管理员密钥",
                description="系统自动创建的管理员密钥，请立即更换",
                is_admin=True,
                is_active=True,
                requests_per_minute=1000,
                requests_per_day=100000
            )
            db.add(default_admin_key)
            db.commit()
            print("=" * 60)
            print("⚠️  创建了默认管理员 API 密钥:")
            print(f"   密钥: {default_key}")
            print("   请立即登录管理面板后创建新的管理员密钥并删除此默认密钥!")
            print("=" * 60)
    finally:
        db.close()


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
