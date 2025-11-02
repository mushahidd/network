"""
FastAPI application entry point for ConnectHub
Community Business Network Platform with OAuth authentication
"""
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from jinja2 import Environment, FileSystemLoader
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
# This must happen before importing settings
load_dotenv()

from app.config import settings
from app.database import engine, Base
from app.routes import home, auth, dashboard, business, profile, search
from app.middleware import UserContextMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI Application Initialization
# ============================================================================

app = FastAPI(
    title="ConnectHub",
    description="Community Business Network Platform",
    version="1.0.0"
)

# ============================================================================
# Middleware Configuration
# ============================================================================

# Session Middleware - MUST be added first for OAuth state management
# This handles session cookies for storing OAuth state tokens and user sessions
# SECRET_KEY must be set in .env file for secure session encryption
# For production, use a strong random secret (e.g., openssl rand -hex 32)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,  # 30 days default
    same_site="lax",  # CSRF protection
    https_only=False  # Allow HTTP for localhost, set True in production with HTTPS
)

# CORS Middleware - Allows cross-origin requests
# Configure appropriately for production (don't use allow_origins=["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to specific domains in production
    allow_credentials=True,  # Required for OAuth callbacks
    allow_methods=["*"],
    allow_headers=["*"],
)

# User Context Middleware - Automatically inject user data into all requests
# Makes current user available to all templates
app.add_middleware(UserContextMiddleware)

# ============================================================================
# Static Files & Templates
# ============================================================================

# Serve static files (CSS, JS, images, uploads)
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    logger.info(f"Static files mounted at /static from {static_path}")

# Templates are initialized per-route in their respective router files
# This allows each route module to have its own template environment

# ============================================================================
# Database Initialization
# ============================================================================

@app.on_event("startup")
async def startup():
    """
    Initialize database on application startup.
    Creates all tables if they don't exist (SQLAlchemy metadata).
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)
        # App can still start, but database features won't work

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on application shutdown"""
    logger.info("Shutting down ConnectHub...")

# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """
    Handle 404 Not Found errors.
    Renders custom 404.html template with navigation options.
    """
    templates_path = os.path.join(os.path.dirname(__file__), "templates")
    jinja_env = Environment(loader=FileSystemLoader(templates_path))
    try:
        template = jinja_env.get_template("errors/404.html")
        return HTMLResponse(
            content=template.render(request=request),
            status_code=404
        )
    except Exception as e:
        logger.error(f"Error rendering 404 template: {e}", exc_info=True)
        # Fallback HTML if template is missing
        error_html = """
        <html>
        <head><title>404 Not Found</title></head>
        <body style="font-family: Arial; padding: 50px; text-align: center;">
            <h1>404 - Page Not Found</h1>
            <p>The page you're looking for doesn't exist.</p>
            <a href="/">Go Home</a>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=404)

@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """
    Handle 500 Internal Server errors.
    Renders custom 500.html template with error details.
    Logs error for debugging while showing user-friendly message.
    """
    templates_path = os.path.join(os.path.dirname(__file__), "templates")
    jinja_env = Environment(loader=FileSystemLoader(templates_path))
    try:
        template = jinja_env.get_template("errors/500.html")
        logger.error(f"500 Server Error: {exc}", exc_info=True)
        return HTMLResponse(
            content=template.render(request=request, error=str(exc)),
            status_code=500
        )
    except Exception as e:
        logger.error(f"Error rendering 500 template: {e}", exc_info=True)
        # Fallback HTML if template is missing
        error_html = f"""
        <html>
        <head><title>500 Server Error</title></head>
        <body style="font-family: Arial; padding: 50px; text-align: center;">
            <h1>500 Server Error</h1>
            <p>Something went wrong on our end. We're working on fixing it.</p>
            <p><small>Error: {str(exc)}</small></p>
            <a href="/">Go Home</a>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle request validation errors (422 Unprocessable Entity).
    Returns JSON response with validation error details.
    """
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body}
    )

# ============================================================================
# Route Registration
# ============================================================================
# IMPORTANT: Route order matters in FastAPI!
# More specific routes must be registered before generic ones.
# This prevents route conflicts where a generic route catches a specific path.

# Home router - handles root "/" and static pages (about, contact)
# Must be first to handle the root route
app.include_router(home.router, tags=["Home"])

# Auth router - handles OAuth authentication
# Routes:
#   - /auth/login - Login page
#   - /auth/google - Initiate Google OAuth
#   - /auth/google/callback - Google OAuth callback (redirect URI)
#   - /auth/microsoft - Initiate Microsoft OAuth
#   - /auth/microsoft/callback - Microsoft OAuth callback
#   - /auth/logout - Logout endpoint
# OAuth Redirect URI Configuration:
#   For localhost: http://localhost:8080/auth/google/callback
#   For production: https://yourdomain.com/auth/google/callback
#   Must match exactly in Google Cloud Console OAuth client settings
app.include_router(auth.router, prefix="/auth", tags=["Auth"])

# Business router - handles business listings and CRUD operations
# Routes include:
#   - /businesses - Business directory
#   - /business/{slug} - Business detail page
#   - /dashboard/business/new - Create new business form
#   - /dashboard/business/{id}/edit - Edit business form
# Registered BEFORE dashboard to ensure /dashboard/business/* routes are matched correctly
app.include_router(business.router, tags=["Business"])

# Profile router - handles professional profiles
# Routes include:
#   - /professionals - Professional directory
#   - /profile/{slug} - Profile detail page
#   - /dashboard/profile/edit - Edit profile form
# Registered BEFORE dashboard for same reason as business router
app.include_router(profile.router, tags=["Profile"])

# Search router - unified search across businesses and professionals
app.include_router(search.router, prefix="/search", tags=["Search"])

# Dashboard router - user dashboard (MUST be last)
# Routes:
#   - /dashboard - Main dashboard
# Registered LAST because it has a catch-all route at /dashboard
# If registered first, it would intercept /dashboard/business/* and /dashboard/profile/*
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

# ============================================================================
# Startup Information
# ============================================================================

@app.on_event("startup")
async def log_startup_info():
    """Log application startup information"""
    logger.info("=" * 70)
    logger.info("🚀 ConnectHub Application Starting")
    logger.info("=" * 70)
    logger.info(f"📁 Base URL: {settings.BASE_URL}")
    logger.info(f"🔐 Google OAuth: {'✅ Configured' if settings.GOOGLE_CLIENT_ID else '❌ Not configured (use Test Login)'}")
    logger.info(f"🔐 Microsoft OAuth: {'✅ Configured' if settings.MICROSOFT_CLIENT_ID else '❌ Not configured'}")
    logger.info(f"🗄️  Database: {settings.DATABASE_URL.split('://')[0]}")
    logger.info(f"🔑 Session Secret: {'✅ Set' if settings.SECRET_KEY != 'your-secret-key-change-in-production' else '⚠️  Using default (not secure!)'}")
    logger.info("=" * 70)
    logger.info("📚 API Documentation: /docs")
    logger.info("🔍 Alternative docs: /redoc")
    logger.info("=" * 70)

# ============================================================================
# Application Ready
# ============================================================================

# Note: The root "/" route is handled by home.router
# All other routes are organized by feature area and registered above
# Route order is critical - more specific routes must come before generic ones

@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok"}


"""
Run ConnectHub FastAPI application
Handles dynamic PORT from Railway environment
"""
import os
import uvicorn

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))  # Default to 8080 if PORT is not set
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

@app.get("/debug/oauth_redirect")
async def debug_redirect_uri():
    from app.config import settings
    return {"redirect_uri": f"{settings.BASE_URL}/auth/google/callback"}

@router.get("/google/login")
async def login_google(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, str(redirect_uri))

@router.get("/auth/google/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    # Handle user authentication
    return RedirectResponse(url="/dashboard")










