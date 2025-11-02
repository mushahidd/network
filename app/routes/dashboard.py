"""
Dashboard routes
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional

from app.database import get_db
from app.models import User, Business, ProfessionalProfile
from app.utils.auth import require_auth
from app.utils.templates import render_template

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth)
):
    """User dashboard"""
    try:
        import logging
        logging.info(f"Dashboard accessed by user: {user.email if user else 'None'}, id: {user.id if user else 'None'}")
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        user_id_str = str(user.id)
        
        # Get user's businesses and extract data to avoid greenlet errors
        user_businesses = []
        businesses_data = []
        try:
            businesses_query = select(Business).where(Business.user_id == user_id_str)
            businesses_result = await db.execute(businesses_query)
            user_businesses = businesses_result.scalars().all()
            
            # Extract business data before rendering
            for business in user_businesses:
                businesses_data.append({
                    "id": str(business.id),
                    "slug": business.slug,
                    "business_name": business.business_name,
                    "tagline": business.tagline,
                    "logo_url": business.logo_url,
                    "category": business.category.value if business.category else None,
                })
        except Exception as e:
            logging.warning(f"Error fetching businesses: {e}")
            user_businesses = []
        
        # Get featured businesses for dashboard
        featured_businesses_data = []
        try:
            featured_query = select(Business).where(
                Business.is_published == True
            ).order_by(Business.view_count.desc()).limit(3)
            featured_result = await db.execute(featured_query)
            featured_businesses = featured_result.scalars().all()
            
            # Extract featured business data
            for business in featured_businesses:
                if business.slug:  # Only add businesses with valid slugs
                    featured_businesses_data.append({
                        "id": str(business.id),
                        "slug": str(business.slug).strip(),  # Ensure slug is string and trimmed
                        "business_name": business.business_name or "Unnamed Business",
                        "tagline": business.tagline or "No tagline",
                        "logo_url": business.logo_url,
                        "category": business.category.value if business.category else None,
                        "location": business.location or "",
                    })
                    logging.info(f"Added featured business: {business.business_name}, slug: {business.slug}")
                else:
                    logging.warning(f"Business {business.business_name} (id: {business.id}) has no slug, skipping")
        except Exception as e:
            logging.error(f"Error fetching featured businesses: {e}", exc_info=True)
        
        # Get user's professional profile
        user_profile = None
        try:
            profile_query = select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id_str)
            profile_result = await db.execute(profile_query)
            user_profile = profile_result.scalar_one_or_none()
        except Exception as e:
            logging.warning(f"Error fetching profile: {e}")
            user_profile = None
        
        # Calculate stats
        total_connections = 0  # Placeholder for now
        total_profile_views = 0
        try:
            for business in user_businesses:
                total_profile_views += business.view_count or 0
        except:
            pass
        if user_profile:
            total_profile_views += user_profile.view_count or 0
        
        total_messages = 0  # Placeholder for now
        
        # Get suggested connections (random users for MVP)
        # Use try-except to handle cases where there are no other users
        suggested_users_data = []
        try:
            suggested_query = select(User).options(
                selectinload(User.professional_profile)
            ).where(
                User.id != str(user.id)
            ).limit(3)
            suggested_result = await db.execute(suggested_query)
            suggested_users = suggested_result.scalars().all()
            
            # Convert to dicts to avoid lazy loading in template
            for suggested in suggested_users:
                user_dict = {
                    "id": str(suggested.id),
                    "email": suggested.email,
                    "display_name": suggested.display_name,
                    "profile_picture_url": suggested.profile_picture_url,
                    "professional_profile": None
                }
                
                # Add professional profile if exists
                if suggested.professional_profile:
                    user_dict["professional_profile"] = {
                        "id": str(suggested.professional_profile.id),
                        "slug": suggested.professional_profile.slug,
                        "full_name": suggested.professional_profile.full_name,
                        "headline": suggested.professional_profile.headline,
                    }
                
                suggested_users_data.append(user_dict)
        except Exception as e:
            logging.warning(f"Could not fetch suggested users: {e}")
            suggested_users_data = []
        
        # Calculate profile completion
        profile_completion = 0
        completion_items = []
        
        if user_profile:
            profile_completion += 20
            completion_items.append({"name": "Professional Profile", "complete": True})
        else:
            completion_items.append({"name": "Professional Profile", "complete": False})
        
        if user_businesses:
            profile_completion += 20
            completion_items.append({"name": "Business Listing", "complete": True})
        else:
            completion_items.append({"name": "Business Listing", "complete": False})
        
        if user.display_name:
            profile_completion += 10
            completion_items.append({"name": "Display Name", "complete": True})
        else:
            completion_items.append({"name": "Display Name", "complete": False})
        
        if user.profile_picture_url:
            profile_completion += 10
            completion_items.append({"name": "Profile Picture", "complete": True})
        else:
            completion_items.append({"name": "Profile Picture", "complete": False})
        
        if user_profile and user_profile.bio:
            profile_completion += 10
            completion_items.append({"name": "Bio", "complete": True})
        elif not user_profile:
            completion_items.append({"name": "Bio", "complete": False})
        
        if user_profile and user_profile.skills and len(user_profile.skills) >= 3:
            profile_completion += 10
            completion_items.append({"name": "Skills (3+)", "complete": True})
        elif not user_profile:
            completion_items.append({"name": "Skills (3+)", "complete": False})
        
        if user_profile and user_profile.linkedin_url:
            profile_completion += 10
            completion_items.append({"name": "LinkedIn URL", "complete": True})
        elif not user_profile:
            completion_items.append({"name": "LinkedIn URL", "complete": False})
        
        if user_profile and user_profile.how_i_can_help:
            profile_completion += 10
            completion_items.append({"name": "How I Can Help", "complete": True})
        elif not user_profile:
            completion_items.append({"name": "How I Can Help", "complete": False})
        
        # Extract profile data if exists
        profile_data = None
        if user_profile:
            profile_data = {
                "id": str(user_profile.id),
                "slug": user_profile.slug,
                "full_name": user_profile.full_name,
                "headline": user_profile.headline,
            }
        
        # Extract user data
        user_data = {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "profile_picture_url": user.profile_picture_url,
        }
        
        return render_template(
            "dashboard.html",
            request,
            user=user_data,
            businesses=businesses_data,
            profile=profile_data,
            featured_businesses=featured_businesses_data,
            stats={
                "connections": total_connections,
                "profile_views": total_profile_views,
                "messages": total_messages
            },
            suggested_users=suggested_users_data,
            profile_completion=profile_completion,
            completion_items=completion_items,
            recent_activity=[]  # Placeholder for now
        )
    except Exception as e:
        import logging
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Dashboard error: {e}\n{error_details}", exc_info=True)
        # Return a simple error page instead of crashing
        from fastapi.responses import HTMLResponse
        error_html = f"""
        <html>
        <head><title>Dashboard Error</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 50px; max-width: 800px; margin: 0 auto; }}
            .error-box {{ background: #fee; border: 1px solid #fcc; padding: 20px; border-radius: 5px; margin: 20px 0; }}
            pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; font-size: 12px; }}
        </style>
        </head>
        <body>
            <h1>Dashboard Error</h1>
            <div class="error-box">
                <p><strong>Error:</strong> {str(e)}</p>
            </div>
            <details>
                <summary>Technical Details (click to expand)</summary>
                <pre>{error_details}</pre>
            </details>
            <p>
                <a href="/">Go Home</a> | 
                <a href="/dashboard">Try Again</a> |
                <a href="/auth/logout">Logout</a>
            </p>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)
