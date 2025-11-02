"""
Authentication utilities
"""
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt as pyjwt
from datetime import datetime, timedelta

from app.config import settings
from app.database import get_db
from app.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


security = HTTPBearer()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Data to encode in token
        expires_delta: Optional expiration delta
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = pyjwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode a JWT access token.
    
    Args:
        token: JWT token to decode
        
    Returns:
        Decoded token data
        
    Raises:
        HTTPException: If token is invalid
    """
    try:
        payload = pyjwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except pyjwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )


async def get_current_user(request: Request, db: AsyncSession) -> Optional[User]:
    """
    Get current user from request (from session cookie or JWT token).
    
    Args:
        request: FastAPI request object
        db: Database session
        
    Returns:
        User object or None
    """
    # Try to get token from Authorization header
    authorization: str = request.headers.get("Authorization")
    if authorization:
        try:
            scheme, token = authorization.split()
            if scheme.lower() == "bearer":
                payload = decode_access_token(token)
                user_id = payload.get("sub")
                if user_id:
                    result = await db.execute(select(User).where(User.id == user_id))
                    user = result.scalar_one_or_none()
                    return user
        except ValueError:
            pass
    
    # Try to get user from session cookie
    session_token = request.cookies.get("session_token")
    if session_token:
        try:
            payload = decode_access_token(session_token)
            user_id = payload.get("sub")
            if user_id:
                # SQLite uses String(36) for UUIDs, convert to string
                user_id_str = str(user_id)
                try:
                    result = await db.execute(select(User).where(User.id == user_id_str))
                    user = result.scalar_one_or_none()
                    if user:
                        return user
                except Exception as e:
                    logging.error(f"Error querying user by id {user_id_str}: {e}")
                    # Try direct comparison
                    try:
                        result = await db.execute(select(User).where(User.id == user_id))
                        user = result.scalar_one_or_none()
                        return user
                    except:
                        pass
        except Exception as e:
            # Log error for debugging but don't fail
            import logging
            logging.debug(f"Error getting user from session: {e}")
            pass
    
    return None


async def require_auth(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Require authentication, raise exception if not authenticated.
    
    Args:
        request: FastAPI request object
        db: Database session
        
    Returns:
        User object
        
    Raises:
        HTTPException: If user is not authenticated
    """
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user

