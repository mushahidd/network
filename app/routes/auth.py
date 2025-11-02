"""
Authentication routes (OAuth)
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

from app.config import settings
from app.database import get_db
from app.models import User
from app.utils.auth import create_access_token
from app.utils.password import hash_password, verify_password
from jinja2 import Environment, FileSystemLoader
import os

# Templates for auth
templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_path))


def render_template(template_name: str, request: Request, **context):
    """Render Jinja2 template"""
    template = jinja_env.get_template(template_name)
    return HTMLResponse(content=template.render(request=request, **context))

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    error: Optional[str] = None,
    register: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Login page - shows login options"""
    from app.utils.auth import get_current_user
    
    # Check if user is already logged in
    user = await get_current_user(request, db)
    
    # Check if Microsoft is configured
    microsoft_configured = bool(settings.MICROSOFT_CLIENT_ID and settings.MICROSOFT_CLIENT_SECRET)
    google_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    
    # Error message handling
    error_message = None
    if error == "oauth_not_configured":
        error_message = "Google OAuth is not configured. Please use Test Login or set up Google OAuth credentials in .env file."
    elif error == "deleted_client":
        error_message = "The Google OAuth client ID you're using was deleted. Please create a new OAuth client or use Test Login."
    elif error == "invalid_client_id":
        error_message = "The Google OAuth Client ID format is invalid. Please check your .env file and ensure it ends with .apps.googleusercontent.com"
    
    # Determine if we should show register form by default
    show_register = register is not None
    
    return render_template(
        "auth/login.html", 
        request, 
        user=user,
        microsoft_configured=microsoft_configured,
        google_configured=google_configured,
        error_message=error_message,
        show_register=show_register
    )


@router.get("/google")
async def google_login(request: Request):
    """Redirect to Google OAuth consent screen"""
    # Check if Google OAuth is properly configured
    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    
    # Validate that client ID exists and looks valid
    if not client_id or not client_id.strip():
        logging.warning("Google OAuth not configured - missing GOOGLE_CLIENT_ID")
        return RedirectResponse(
            url="/auth/login?error=oauth_not_configured",
            status_code=status.HTTP_302_FOUND
        )
    
    # Check if client ID looks like a deleted/invalid one (old deleted client)
    if "280308881889-79s4g1bqr6bju23lhtaeq13dj65ciju1" in client_id:
        logging.error("Detected deleted Google OAuth client ID - redirecting to setup page")
        return RedirectResponse(
            url="/auth/login?error=deleted_client",
            status_code=status.HTTP_302_FOUND
        )
    
    # Validate client ID format (should end with .apps.googleusercontent.com)
    if not client_id.endswith(".apps.googleusercontent.com"):
        logging.warning(f"Google OAuth Client ID format looks invalid: {client_id[:30]}...")
        return RedirectResponse(
            url="/auth/login?error=invalid_client_id",
            status_code=status.HTTP_302_FOUND
        )
    
    if not client_secret or not client_secret.strip():
        logging.warning("Google OAuth Client Secret is missing")
        return RedirectResponse(
            url="/auth/login?error=oauth_not_configured",
            status_code=status.HTTP_302_FOUND
        )
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state in session (ensure session exists)
    if not hasattr(request, 'session'):
        request.session = {}
    request.session["oauth_state"] = {"provider": "google", "timestamp": datetime.utcnow().isoformat()}
    request.session["state"] = state
    
    # Generate redirect URI - construct manually to ensure exact match
    # Get base URL from request
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/auth/google/callback"
    # Force HTTP for localhost
    if "localhost" in redirect_uri or "127.0.0.1" in redirect_uri:
        redirect_uri = redirect_uri.replace("https://", "http://")
    
    logging.info(f"Google OAuth redirect_uri: {redirect_uri}")
    logging.info(f"Using Google Client ID: {client_id[:30]}...")
    
    # Google OAuth authorization URL
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
    logging.info(f"Redirecting to Google OAuth: {auth_url[:100]}...")
    response = RedirectResponse(url=auth_url)
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    authError: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth callback"""
    # Check for OAuth errors (Google may pass error in authError or error parameter)
    oauth_error = error or authError
    if oauth_error:
        error_msg = error_description or oauth_error
        # Handle specific error types
        if "deleted_client" in oauth_error.lower():
            error_msg = "The Google OAuth client was deleted. Please create a new OAuth client or use Test Login for development."
        logging.error(f"Google OAuth error: {oauth_error}, description: {error_msg}")
        return render_template("auth/error.html", request, error=oauth_error, error_description=error_msg)
    
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code"
        )
    
    # State validation is optional - just log if mismatch
    if hasattr(request, 'session'):
        session_state = request.session.get("state")
        if session_state and session_state != state:
            logging.warning(f"State mismatch: session={session_state[:10] if session_state else None}..., received={state[:10] if state else None}...")
        
        # Clean up state from session
        if "state" in request.session:
            del request.session["state"]
        if "oauth_state" in request.session:
            del request.session["oauth_state"]
    
    # Generate redirect URI - construct manually to ensure exact match
    # Get base URL from request
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/auth/google/callback"
    # Force HTTP for localhost
    if "localhost" in redirect_uri or "127.0.0.1" in redirect_uri:
        redirect_uri = redirect_uri.replace("https://", "http://")
    
    logging.info(f"Google OAuth callback redirect_uri: {redirect_uri}")
    
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
        token_response = await client.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
        access_token = tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No access token received from Google"
            )
        
        # Get user info
        user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_response = await client.get(user_info_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
    
    # Extract user information
    email = user_data.get("email")
    oauth_id = user_data.get("id")
    display_name = user_data.get("name") or email.split("@")[0]
    profile_picture = user_data.get("picture")
    
    # Debug logging
    logging.info(f"Google user data received: email={email}, name={display_name}")
    logging.info(f"Profile picture URL from Google: {profile_picture}")
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by Google"
        )
    
    # Find or create user in database
    try:
        result = await db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update existing user
            user.last_login_at = datetime.utcnow()
            if profile_picture:
                user.profile_picture_url = profile_picture
                logging.info(f"Updated profile picture for {email}: {profile_picture}")
            else:
                logging.warning(f"No profile picture received from Google for {email}")
            await db.commit()
            await db.refresh(user)
            logging.info(f"User logged in: {email}, id: {user.id}, picture_url: {user.profile_picture_url}")
        else:
            # Create new user
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
            logging.info(f"New user created: {email}, id: {user.id}, picture_url: {profile_picture}")
        
        # Ensure user.id is string for token
        user_id_str = str(user.id)
        
        # Create session token
        token = create_access_token(data={"sub": user_id_str})
        
        # Redirect to dashboard with session cookie
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="session_token",
            value=token,
            max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
            httponly=True,
            secure=settings.BASE_URL.startswith("https"),
            samesite="lax"
        )
        logging.info(f"Redirecting user {email} to dashboard with token")
        return response
        
    except Exception as e:
        logging.error(f"Database error during login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving user to database: {str(e)}"
        )


@router.get("/microsoft")
async def microsoft_login(request: Request):
    """Redirect to Microsoft OAuth consent screen"""
    if not settings.MICROSOFT_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Microsoft OAuth not configured"
        )
    
    # Generate state token
    state = secrets.token_urlsafe(32)
    
    # Store state in session
    if "oauth_state" not in request.session:
        request.session["oauth_state"] = {}
    request.session["oauth_state"] = {"provider": "microsoft", "timestamp": datetime.utcnow().isoformat()}
    request.session["state"] = state
    
    # Microsoft OAuth authorization URL
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": f"{settings.BASE_URL}/auth/microsoft/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "response_mode": "query"
    }
    
    auth_url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Handle Microsoft OAuth callback"""
    if error:
        return render_template("auth/error.html", request, error=error)
    
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state parameter"
        )
    
    # Verify state from session
    session_state = request.session.get("state")
    session_oauth = request.session.get("oauth_state", {})
    
    if not session_state or session_state != state:
        # Clear invalid state
        if "state" in request.session:
            del request.session["state"]
        if "oauth_state" in request.session:
            del request.session["oauth_state"]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter. Please try logging in again."
        )
    
    # Clean up state from session
    if "state" in request.session:
        del request.session["state"]
    if "oauth_state" in request.session:
        del request.session["oauth_state"]
    
    # Exchange code for token
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    token_data = {
        "code": code,
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "client_secret": settings.MICROSOFT_CLIENT_SECRET,
        "redirect_uri": f"{settings.BASE_URL}/auth/microsoft/callback",
        "grant_type": "authorization_code",
        "scope": "openid email profile"
    }
    
    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, data=token_data)
        token_response.raise_for_status()
        tokens = token_response.json()
        access_token = tokens.get("access_token")
        
        # Get user info from Microsoft Graph API
        user_info_url = "https://graph.microsoft.com/v1.0/me"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_response = await client.get(user_info_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
        
        # Also get profile picture if available
        try:
            photo_response = await client.get(
                "https://graph.microsoft.com/v1.0/me/photo/$value",
                headers=headers
            )
            # Microsoft returns image binary, we'll skip it for now
            profile_picture = None
        except:
            profile_picture = None
    
    # Extract user information (Microsoft uses different field names)
    email = user_data.get("mail") or user_data.get("userPrincipalName")
    oauth_id = user_data.get("id")
    display_name = user_data.get("displayName") or user_data.get("givenName", "") + " " + user_data.get("surname", "")
    if not display_name.strip():
        display_name = email.split("@")[0] if email else "User"
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by Microsoft"
        )
    
    # Find or create user
    result = await db.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Update last login
        user.last_login_at = datetime.utcnow()
        if profile_picture:
            user.profile_picture_url = profile_picture
        await db.commit()
    else:
        # Create new user
        user = User(
            email=email,
            oauth_provider="microsoft",
            oauth_id=str(oauth_id),
            display_name=display_name,
            profile_picture_url=profile_picture,
            last_login_at=datetime.utcnow()
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    # Create session token
    token = create_access_token(data={"sub": str(user.id)})
    
    # Redirect to dashboard with session cookie
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
        httponly=True,
        secure=settings.BASE_URL.startswith("https"),
        samesite="lax"
    )
    return response


@router.post("/register")
async def register(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Register new user with email and password"""
    from fastapi import Form
    
    # Get form data
    form = await request.form()
    email = form.get("email")
    password = form.get("password")
    display_name = form.get("display_name") or email.split("@")[0]
    
    # Validate inputs
    if not email or not password:
        return render_template(
            "auth/login.html",
            request,
            error_message="Email and password are required",
            google_configured=bool(settings.GOOGLE_CLIENT_ID),
            microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
            show_register=True,
            form_email=email,
            form_display_name=display_name
        )
    
    if len(password) < 8:
        return render_template(
            "auth/login.html",
            request,
            error_message="Password must be at least 8 characters long",
            google_configured=bool(settings.GOOGLE_CLIENT_ID),
            microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
            show_register=True,
            form_email=email,
            form_display_name=display_name
        )
    
    try:
        # Check if user already exists
        result = await db.execute(
            select(User).where(User.email == email)
        )
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            return render_template(
                "auth/login.html",
                request,
                error_message="An account with this email already exists. Please sign in instead.",
                google_configured=bool(settings.GOOGLE_CLIENT_ID),
                microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
                show_register=False,
                form_email=email
            )
        
        # Create new user
        password_hashed = hash_password(password)
        user = User(
            email=email,
            password_hash=password_hashed,
            display_name=display_name,
            oauth_provider=None,
            oauth_id=None,
            last_login_at=datetime.utcnow(),
            email_verified=False  # Can implement email verification later
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        logging.info(f"New user registered: {email}, id: {user.id}")
        
        # Create session token
        user_id_str = str(user.id)
        token = create_access_token(data={"sub": user_id_str})
        
        # Redirect to dashboard with session cookie
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="session_token",
            value=token,
            max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
            httponly=True,
            secure=settings.BASE_URL.startswith("https"),
            samesite="lax"
        )
        return response
        
    except Exception as e:
        logging.error(f"Registration error: {e}", exc_info=True)
        return render_template(
            "auth/login.html",
            request,
            error_message=f"Registration failed: {str(e)}",
            google_configured=bool(settings.GOOGLE_CLIENT_ID),
            microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
            show_register=True,
            form_email=email,
            form_display_name=display_name
        )


@router.post("/login")
async def login(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password"""
    from fastapi import Form
    
    # Get form data
    form = await request.form()
    email = form.get("email")
    password = form.get("password")
    
    # Validate inputs
    if not email or not password:
        return render_template(
            "auth/login.html",
            request,
            error_message="Email and password are required",
            google_configured=bool(settings.GOOGLE_CLIENT_ID),
            microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
            form_email=email
        )
    
    try:
        # Find user
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user:
            return render_template(
                "auth/login.html",
                request,
                error_message="No account found with this email. Please register first.",
                google_configured=bool(settings.GOOGLE_CLIENT_ID),
                microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
                show_register=True,
                form_email=email
            )
        
        # Check if user registered with OAuth
        if user.oauth_provider:
            return render_template(
                "auth/login.html",
                request,
                error_message=f"This email is registered with {user.oauth_provider}. Please use '{user.oauth_provider}' login instead.",
                google_configured=bool(settings.GOOGLE_CLIENT_ID),
                microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
                form_email=email
            )
        
        # Verify password
        if not user.password_hash or not verify_password(password, user.password_hash):
            return render_template(
                "auth/login.html",
                request,
                error_message="Incorrect password. Please try again.",
                google_configured=bool(settings.GOOGLE_CLIENT_ID),
                microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
                form_email=email
            )
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        
        logging.info(f"User logged in: {email}, id: {user.id}")
        
        # Create session token
        user_id_str = str(user.id)
        token = create_access_token(data={"sub": user_id_str})
        
        # Redirect to dashboard with session cookie
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="session_token",
            value=token,
            max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
            httponly=True,
            secure=settings.BASE_URL.startswith("https"),
            samesite="lax"
        )
        return response
        
    except Exception as e:
        logging.error(f"Login error: {e}", exc_info=True)
        return render_template(
            "auth/login.html",
            request,
            error_message=f"Login failed: {str(e)}",
            google_configured=bool(settings.GOOGLE_CLIENT_ID),
            microsoft_configured=bool(settings.MICROSOFT_CLIENT_ID),
            form_email=email
        )


@router.get("/logout")
async def logout(request: Request):
    """Logout user"""
    # Clear session
    request.session.clear()
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="session_token")
    return response


@router.get("/debug/me")
async def debug_me(request: Request, db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check current user data"""
    from app.utils.auth import get_current_user
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
