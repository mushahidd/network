"""
Application configuration from environment variables
"""
from functools import lru_cache
import os


class Settings:
    """Application settings"""
    
    # App
    APP_NAME: str = "ConnectHub"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # Database
    # Default to SQLite for easy local development, can use PostgreSQL for production
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./connecthub.db"  # SQLite for local dev, no setup needed
    )
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 30
    
    # OAuth - Google
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    
    # OAuth - Microsoft
    MICROSOFT_CLIENT_ID: str = os.getenv("MICROSOFT_CLIENT_ID", "")
    MICROSOFT_CLIENT_SECRET: str = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    
    # URLs
    # Default to port 8080 for local development (matches run.py)
    # For production, set BASE_URL in .env to your actual domain
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8080")
    
    # File Uploads
    UPLOAD_DIR: str = "app/static/uploads"
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024  # 5MB
    ALLOWED_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".webp"}


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Note: Settings are cached. If you change .env file, restart the server
    or clear the cache by calling get_settings.cache_clear()
    """
    return Settings()

def reload_settings():
    """Clear settings cache to reload from .env file"""
    get_settings.cache_clear()


settings = get_settings()

