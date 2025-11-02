"""
SQLAlchemy database models
"""
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from datetime import datetime
import os

from app.database import Base

# Support both PostgreSQL (UUID) and SQLite (String)
# Detect database type from DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./connecthub.db")
if "sqlite" in DATABASE_URL.lower():
    # SQLite - use String(36) for UUIDs (simpler, compatible)
    UUIDType = String(36)
    def uuid_default():
        return str(uuid.uuid4())
else:
    # PostgreSQL - use native UUID type
    try:
        from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
        UUIDType = PostgresUUID(as_uuid=True)
        def uuid_default():
            return uuid.uuid4()
    except:
        UUIDType = String(36)
        def uuid_default():
            return str(uuid.uuid4())


class BusinessCategory(str, enum.Enum):
    """Business category enum"""
    TECHNOLOGY = "Technology"
    MARKETING = "Marketing"
    FINANCE = "Finance"
    HEALTHCARE = "Healthcare"
    EDUCATION = "Education"
    OTHER = "Other"


class AvailabilityStatus(str, enum.Enum):
    """Professional availability status"""
    AVAILABLE = "Available"
    BUSY = "Busy"
    NOT_LOOKING = "Not Looking"


class User(Base):
    """User model for OAuth and email/password accounts"""
    __tablename__ = "users"
    
    id = Column(UUIDType, primary_key=True, default=uuid_default)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # For email/password auth
    oauth_provider = Column(String(50), nullable=True)  # google, microsoft, or None for email/password
    oauth_id = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=False)
    profile_picture_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)  # For email/password users
    
    # Relationships
    businesses = relationship("Business", back_populates="owner", cascade="all, delete-orphan")
    professional_profile = relationship("ProfessionalProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.email}>"


class Business(Base):
    """Business listing model"""
    __tablename__ = "businesses"
    
    id = Column(UUIDType, primary_key=True, default=uuid_default)
    user_id = Column(UUIDType, ForeignKey("users.id"), nullable=False)
    business_name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    tagline = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(Enum(BusinessCategory), nullable=False, index=True)
    industry_tags = Column(JSON, nullable=True)  # Array of strings
    logo_url = Column(String(500), nullable=True)
    cover_image_url = Column(String(500), nullable=True)
    contact_email = Column(String(255), nullable=False)
    contact_phone = Column(String(50), nullable=True)
    website_url = Column(String(500), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    location = Column(String(255), nullable=False)
    is_published = Column(Boolean, default=True)
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="businesses")
    
    def __repr__(self):
        return f"<Business {self.business_name}>"


class ProfessionalProfile(Base):
    """Professional profile model"""
    __tablename__ = "professional_profiles"
    
    id = Column(UUIDType, primary_key=True, default=uuid_default)
    user_id = Column(UUIDType, ForeignKey("users.id"), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    headline = Column(String(100), nullable=False)
    bio = Column(String(300), nullable=False)
    profile_summary = Column(Text, nullable=True)
    skills = Column(JSON, nullable=True)  # Array of strings
    linkedin_url = Column(String(500), nullable=False)
    portfolio_url = Column(String(500), nullable=True)
    how_i_can_help = Column(Text, nullable=True)
    availability_status = Column(Enum(AvailabilityStatus), default=AvailabilityStatus.AVAILABLE)
    consent_show_contact = Column(Boolean, default=False)
    consent_show_linkedin = Column(Boolean, default=True)
    view_count = Column(Integer, default=0)
    is_published = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="professional_profile")
    
    def __repr__(self):
        return f"<ProfessionalProfile {self.full_name}>"

