"""
Middleware for ConnectHub
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import AsyncSessionLocal
from app.utils.auth import get_current_user
import logging

logger = logging.getLogger(__name__)


class UserContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject current user into request state.
    Makes user available to all templates without manual passing.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Add user to request state
        request.state.user = None
        request.state.user_data = None
        
        # Get current user if authenticated
        try:
            async with AsyncSessionLocal() as db:
                user = await get_current_user(request, db)
                if user:
                    request.state.user = user
                    # Create serializable user data dict
                    request.state.user_data = {
                        "id": str(user.id),
                        "email": user.email,
                        "display_name": user.display_name,
                        "profile_picture_url": user.profile_picture_url,
                    }
        except Exception as e:
            logger.debug(f"Could not load user in middleware: {e}")
            pass
        
        response = await call_next(request)
        return response
