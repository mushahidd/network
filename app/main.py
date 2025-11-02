"""
FastAPI application entry point for ConnectHub
Community Business Network Platform with OAuth authentication
"""
from fastapi import FastAPI, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from jinja2 import Environment, FileSystemLoader
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
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

app = FastAPI(
    title="ConnectHub",
    description="Community Business Network Platform",
    version="1.0.0"
)

# ============================================================================

# Session Middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=60 * 60 * 24 * settings.ACCESS_TOKEN_EXPIRE_DAYS,
    same_site="lax",
    https_only=False
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# User Context Middleware
app.add_middleware(UserContextMiddleware)

# ============================================================================

# Static Files
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    logger.info(f"Static files mounted at /static from {static_path}")

# ============================================================================

# Database Initialization
@app.on_event("startup")
async def startup():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down ConnectHub...")

# ============================================================================

# Error Handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    templates_path = os.path.join(os.path.dirname(__file__), "templates")
    jinja_env = Environment(loader=FileSystemLoader(templates_path))
    try:
        template = jinja_env.get_template("errors/404.html")
        return HTMLResponse(content=template.render(request=request), status_code=404)
    except Exception as e:
        logger.error(f"Error rendering 404 template: {e}", exc_info=True)
        return HTMLResponse(content="<h1>404 Not Found</h1>", status_code=404)

@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    templates_path = os.path.join(os.path.dirname(__file__), "templates")
    jinja_env = Environment(loader=FileSystemLoader(templates_path))
    try:
        template = jinja_env.get_template("errors/500.html")
        logger.error(f"500 Server Error: {exc}", exc_info=True)
        return HTMLResponse(content=template.render(request=request, error=str(exc)), status_code=500)
    except Exception as e:
        logger.error(f"Error rendering 500 template: {e}", exc_info=True)
        return HTMLResponse(content=f"<h1>500 Server Error</h1><p>{str(exc)}</p>", status_code=500)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content={"detail": exc.errors(), "body": exc.body})

# ============================================================================

# Route Registration
app.include_router(home.router, tags=["Home"])
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(business.router, tags=["Business"])
app.include_router(profile.router, tags=["Profile"])
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

# ============================================================================

@app.on_event("startup")
async def log_startup_info():
    logger.info("=" * 70)
    logger.info("🚀 ConnectHub Application Starting")
    logger.info("=" * 70)
    logger.info(f"📁 Base URL: {settings.BASE_URL}")
    logger.info(f"🔐 Google OAuth: {'✅ Configured' if settings.GOOGLE_CLIENT_ID else '❌ Not configured'}")
    logger.info(f"🔐 Microsoft OAuth: {'✅ Configured' if settings.MICROSOFT_CLIENT_ID else '❌ Not configured'}")
    logger.info(f"🗄️  Database: {settings.DATABASE_URL.split('://')[0]}")
    logger.info(f"🔑 Session Secret: {'✅ Set' if settings.SECRET_KEY != 'your-secret-key-change-in-production' else '⚠️ Default!'}")
    logger.info("=" * 70)
    logger.info("📚 API Documentation: /docs")
    logger.info("🔍 Alternative docs: /redoc")
    logger.info("=" * 70)

# ============================================================================

@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok"}

@app.get("/debug/oauth_redirect")
async def debug_redirect_uri():
    return {"redirect_uri": f"{settings.BASE_URL}/auth/google/callback"}

# ============================================================================

# Run server
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
