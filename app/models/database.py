"""
Database models for account pool and API keys
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

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


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
