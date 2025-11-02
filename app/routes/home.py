"""
Homepage routes
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.ext.asyncio import AsyncSession
import os

from app.database import get_db
from app.utils.auth import get_current_user
from app.utils.templates import render_template
from app.models import User, Business, ProfessionalProfile
from app.config import settings
from sqlalchemy import select, func
from typing import Optional

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Homepage - Always shows home page, user status is optional"""
    import logging
    logging.info("Homepage request received")
    
    try:
        # Get current user if logged in (optional, don't fail if not logged in)
        # This allows homepage to show for both logged in and logged out users
        user: Optional[User] = None
        user_data = None
        try:
            user = await get_current_user(request, db)
            if user:
                # Extract user data to avoid greenlet errors
                user_data = {
                    "id": str(user.id),
                    "email": user.email,
                    "display_name": user.display_name,
                    "profile_picture_url": user.profile_picture_url,
                }
                logging.info(f"User logged in: {user.email}")
        except Exception as e:
            logging.info(f"User not logged in or error getting user: {e}")
            pass  # User not logged in, that's okay for homepage
        
        # Fetch featured businesses (published, sorted by view_count)
        featured_businesses_data = []
        try:
            businesses_query = select(Business).where(
                Business.is_published == True
            ).order_by(Business.view_count.desc()).limit(3)
            businesses_result = await db.execute(businesses_query)
            featured_businesses = businesses_result.scalars().all()
            
            # Extract business data to avoid greenlet errors
            for business in featured_businesses:
                featured_businesses_data.append({
                    "id": str(business.id),
                    "slug": str(business.slug).strip() if business.slug else None,
                    "business_name": business.business_name or "Unnamed Business",
                    "tagline": business.tagline or "",
                    "logo_url": business.logo_url,
                })
        except Exception as e:
            import logging
            logging.warning(f"Error fetching featured businesses: {e}")
        
        # Fetch featured professionals (published, sorted by view_count)
        featured_professionals_data = []
        try:
            profiles_query = select(ProfessionalProfile).where(
                ProfessionalProfile.is_published == True
            ).order_by(ProfessionalProfile.view_count.desc()).limit(4)
            profiles_result = await db.execute(profiles_query)
            featured_professionals = profiles_result.scalars().all()
            
            # Extract professional data
            for profile in featured_professionals:
                featured_professionals_data.append({
                    "id": str(profile.id),
                    "slug": str(profile.slug).strip() if profile.slug else None,
                    "full_name": profile.full_name,
                    "headline": profile.headline or "",
                })
        except Exception as e:
            import logging
            logging.warning(f"Error fetching featured professionals: {e}")
        
        # Get real statistics from database
        stats = {
            "businesses": 0,
            "professionals": 0,
            "connections": 0
        }
        
        try:
            # Count published businesses
            business_count_query = select(func.count(Business.id)).where(Business.is_published == True)
            business_count_result = await db.execute(business_count_query)
            stats["businesses"] = business_count_result.scalar() or 0
            
            # Count published professional profiles
            profile_count_query = select(func.count(ProfessionalProfile.id)).where(ProfessionalProfile.is_published == True)
            profile_count_result = await db.execute(profile_count_query)
            stats["professionals"] = profile_count_result.scalar() or 0
            
            # Count total users as connections (or you can implement a connections table later)
            user_count_query = select(func.count(User.id))
            user_count_result = await db.execute(user_count_query)
            stats["connections"] = user_count_result.scalar() or 0
            
        except Exception as e:
            logging.warning(f"Error fetching statistics: {e}")
        
        # Check if Microsoft is configured
        microsoft_configured = bool(settings.MICROSOFT_CLIENT_ID and settings.MICROSOFT_CLIENT_SECRET)
        
        logging.info(f"Rendering homepage with {len(featured_businesses_data)} businesses and {len(featured_professionals_data)} professionals")
        logging.info(f"Statistics: {stats['businesses']} businesses, {stats['professionals']} professionals, {stats['connections']} users")
        
        return render_template(
            "home.html",
            request,
            user=user_data,  # Pass extracted user data or None
            featured_businesses=featured_businesses_data,
            featured_professionals=featured_professionals_data,
            microsoft_configured=microsoft_configured,
            stats=stats,
            upcoming_events=[]
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error rendering homepage: {e}\n{error_details}", exc_info=True)
        # Return a simple error page
        from fastapi.responses import HTMLResponse
        error_html = f"""
        <html>
        <head><title>Homepage Error</title></head>
        <body style="font-family: Arial; padding: 50px; text-align: center;">
            <h1>Homepage Error</h1>
            <p>An error occurred while loading the homepage.</p>
            <p><small>Error: {str(e)}</small></p>
            <a href="/">Try Again</a>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)


@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    """About page"""
    return render_template("about.html", request)


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    """Contact page"""
    return render_template("contact.html", request)

