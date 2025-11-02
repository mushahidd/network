"""
Authentication routes (OAuth + Email/Password)
"""
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime
import httpx
import secrets
import logging
from urllib.parse import urlencode
import os

from app.config import settings
from app.database import get_db
from app.models import User
from app.utils.auth import create_access_token, get_current_user
from app.utils.password import hash_password, verify_password
from jinja2 import Environment, FileSystemLoader

# Setup Jinja2 templates
templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_path))


def render_template(template_name: str, request: Request, **context):
    """Render Jinja2 template"""
    template = jinja_env.get_template(template_name)
    return HTMLResponse(content=template.render(request=request, **context))


router = APIRouter()


# ------------------------
# Login Page
# ------------------------
@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Optional[str] = None,
    register: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Login page - shows login options"""
    user = await get_current_user(request, db)
    google_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    microsoft_configured = bool(settings.MICROSOFT_CLIENT_ID and settings.MICROSOFT_CLIENT_SECRET)

    error_message = None
    if error == "oauth_not_configured":
        error_message = "OAuth is not configured. Please contact admin."
    elif error == "deleted_client":
        error_message = "The OAuth client ID was deleted. Please update credentials."
    elif error == "invalid_client_id":
        error_message = "Invalid Google Client ID format."

    show_register = register is not None

    return render_template(
        "auth/login.html",
        request=request,
        user=user,
        google_configured=google_configured,
        microsoft_configured=microsoft_configured,
        error_message=error_message,
        show_register=show_register
    )


# ------------------------
# Google OAuth
# ------------------------
@router.get("/google")
async def google_login(request: Request):
    """Redirect to Google OAuth consent screen"""
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET

    if not client_id or not client_secret:
        logging.warning("Google OAuth not configured")
        return RedirectResponse("/auth/login?error=oauth_not_configured")

    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session["state"] = state
    request.session["oauth_provider"] = "google"

    # Redirect URI must match exactly in Google Cloud Console
    redirect_uri = f"{settings.BASE_URL.rstrip('/')}/auth/google/callback"
    if "localhost" in redirect_uri or "127.0.0.1" in redirect_uri:
        redirect_uri = redirect_uri.replace("https://", "http://")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account"
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    logging.info(f"Redirecting to Google OAuth: {auth_url}")
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth callback"""
    if error:
        return render_template("auth/error.html", request=request, error=error)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    # Validate state
    session_state = request.session.get("state")
    if not session_state or session_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Clean session
    request.session.pop("state", None)
    request.session.pop("oauth_provider", None)

    # Construct redirect_uri
    redirect_uri = f"{settings.BASE_URL.rstrip('/')}/auth/google/callback"
    if "localhost" in redirect_uri or "127.0.0.1" in redirect_uri:
        redirect_uri = redirect_uri.replace("https://", "http://")

    # Exchange code for token
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, data=token_data)
        token_resp.raise_for_status()
        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access token received from Google")

        # Get user info
        user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_resp = await client.get(user_info_url, headers=headers)
        user_resp.raise_for_status()
        user_data = user_resp.json()

    email = user_data.get("email")
    oauth_id = user_data.get("id")
    display_name = user_data.get("name") or email.split("@")[0]
    profile_picture = user_data.get("picture")

    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by Google")

    # Find or create user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        user.last_login_at = datetime.utcnow()
        if profile_picture:
            user.profile_picture_url = profile_picture
        await db.commit()
        await db.refresh(user)
    else:
        user = User(
            email=email,
            oauth_provider="google",
            oauth_id=str(oauth_id),
            display_name=display_name,
            profile_picture_url=profile_picture,
            last_login_at=datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    response = RedirectResponse("/dashboard")
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
        httponly=True,
        secure=settings.BASE_URL.startswith("https"),
        samesite="lax"
    )
    return response


# ------------------------
# Microsoft OAuth
# ------------------------
@router.get("/microsoft")
async def microsoft_login(request: Request):
    if not settings.MICROSOFT_CLIENT_ID:
        return RedirectResponse("/auth/login?error=oauth_not_configured")

    state = secrets.token_urlsafe(32)
    request.session["state"] = state
    request.session["oauth_provider"] = "microsoft"

    redirect_uri = f"{settings.BASE_URL.rstrip('/')}/auth/microsoft/callback"
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "response_mode": "query"
    }

    auth_url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"
    return RedirectResponse(auth_url)


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    if error:
        return render_template("auth/error.html", request=request, error=error)

    if not code or not state or state != request.session.get("state"):
        raise HTTPException(status_code=400, detail="Invalid state or missing parameters")

    # Clean session
    request.session.pop("state", None)
    request.session.pop("oauth_provider", None)

    redirect_uri = f"{settings.BASE_URL.rstrip('/')}/auth/microsoft/callback"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    token_data = {
        "code": code,
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "scope": "openid email profile"
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, data=token_data)
        token_resp.raise_for_status()
        tokens = token_resp.json()
        access_token = tokens.get("access_token")

        user_info_url = "https://graph.microsoft.com/v1.0/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_resp = await client.get(user_info_url, headers=headers)
        user_resp.raise_for_status()
        user_data = user_resp.json()

    email = user_data.get("mail") or user_data.get("userPrincipalName")
    oauth_id = user_data.get("id")
    display_name = user_data.get("displayName") or email.split("@")[0]

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        user.last_login_at = datetime.utcnow()
        await db.commit()
    else:
        user = User(
            email=email,
            oauth_provider="microsoft",
            oauth_id=str(oauth_id),
            display_name=display_name,
            last_login_at=datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    response = RedirectResponse("/dashboard")
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
        httponly=True,
        secure=settings.BASE_URL.startswith("https"),
        samesite="lax"
    )
    return response


# ------------------------
# Email/Password Registration & Login
# ------------------------
@router.post("/register")
async def register(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")
    display_name = form.get("display_name") or email.split("@")[0]

    if not email or not password:
        return render_template("auth/login.html", request=request, error_message="Email and password required", show_register=True)

    if len(password) < 8:
        return render_template("auth/login.html", request=request, error_message="Password must be at least 8 characters", show_register=True)

    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        return render_template("auth/login.html", request=request, error_message="Email already exists. Login instead.")

    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        oauth_provider=None,
        last_login_at=datetime.utcnow()
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    response = RedirectResponse("/dashboard")
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
        httponly=True,
        secure=settings.BASE_URL.startswith("https"),
        samesite="lax"
    )
    return response


@router.post("/login")
async def login(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return render_template("auth/login.html", request=request, error_message="User not found", show_register=True)

    if user.oauth_provider:
        return render_template("auth/login.html", request=request, error_message=f"Use {user.oauth_provider} login instead.")

    if not verify_password(password, user.password_hash):
        return render_template("auth/login.html", request=request, error_message="Incorrect password")

    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    token = create_access_token(data={"sub": str(user.id)})
    response = RedirectResponse("/dashboard")
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
        httponly=True,
        secure=settings.BASE_URL.startswith("https"),
        samesite="lax"
    )
    return response


# ------------------------
# Logout
# ------------------------
@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse("/")
    response.delete_cookie("session_token")
    return response


# ------------------------
# Debug current user
# ------------------------
@router.get("/debug/me")
async def debug_me(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return {"error": "Not logged in"}
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "profile_picture_url": user.profile_picture_url,
        "oauth_provider": user.oauth_provider,
        "last_login_at": str(user.last_login_at)
    }
