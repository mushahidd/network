"""
Search routes
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import Optional

from app.database import get_db
from app.models import User, Business, ProfessionalProfile, BusinessCategory
from app.utils.auth import get_current_user
from jinja2 import Environment, FileSystemLoader
import os

router = APIRouter()

templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_path))


def render_template(template_name: str, request: Request, **context):
    """Render Jinja2 template"""
    template = jinja_env.get_template(template_name)
    return HTMLResponse(content=template.render(request=request, **context))


@router.get("", response_class=HTMLResponse)
async def search(
    request: Request,
    q: Optional[str] = None,
    type: Optional[str] = "all",
    category: Optional[str] = None,
    skill: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """Unified search across businesses and professionals"""
    per_page = 20
    offset = (page - 1) * per_page
    
    businesses = []
    professionals = []
    total_businesses = 0
    total_professionals = 0
    
    # Search businesses
    if type in ("all", "businesses"):
        business_query = select(Business).where(Business.is_published == True)
        
        # Text search
        if q:
            search_filter = f"%{q}%"
            business_query = business_query.where(
                or_(
                    Business.business_name.ilike(search_filter),
                    Business.tagline.ilike(search_filter),
                    Business.description.ilike(search_filter)
                )
            )
        
        # Category filter
        if category:
            try:
                category_enum = BusinessCategory[category.upper()]
                business_query = business_query.where(Business.category == category_enum)
            except KeyError:
                pass
        
        # Count
        count_query = select(func.count()).select_from(business_query.subquery())
        total_result = await db.execute(count_query)
        total_businesses = total_result.scalar() or 0
        
        # Get paginated results
        business_query = business_query.order_by(Business.created_at.desc()).limit(per_page).offset(offset)
        business_result = await db.execute(business_query)
        businesses_list = business_result.scalars().all()
        
        # Extract business data
        businesses_data = []
        for business in businesses_list:
            business_category = business.category
            businesses_data.append({
                "id": str(business.id),
                "slug": business.slug,
                "business_name": business.business_name,
                "tagline": business.tagline,
                "category": business_category,
                "category_value": business_category.value if business_category else None,
                "logo_url": business.logo_url,
                "cover_image_url": business.cover_image_url,
                "location": business.location,
            })
        businesses = businesses_data
    
    # Search professionals
    if type in ("all", "professionals"):
        profile_query = select(ProfessionalProfile).where(ProfessionalProfile.is_published == True)
        
        # Text search
        if q:
            search_filter = f"%{q}%"
            profile_query = profile_query.where(
                or_(
                    ProfessionalProfile.full_name.ilike(search_filter),
                    ProfessionalProfile.headline.ilike(search_filter),
                    ProfessionalProfile.bio.ilike(search_filter)
                )
            )
        
        # Skill filter
        if skill:
            profile_query = profile_query.where(ProfessionalProfile.skills.contains([skill]))
        
        # Count
        count_query = select(func.count()).select_from(profile_query.subquery())
        total_result = await db.execute(count_query)
        total_professionals = total_result.scalar() or 0
        
        # Get paginated results
        profile_query = profile_query.order_by(ProfessionalProfile.created_at.desc()).limit(per_page).offset(offset)
        profile_result = await db.execute(profile_query)
        professionals_list = profile_result.scalars().all()
        
        # Extract professional data
        professionals_data = []
        for profile in professionals_list:
            user_id_str = str(profile.user_id)
            profile_user_data = None
            try:
                user_query = select(User).where(User.id == user_id_str)
                user_result = await db.execute(user_query)
                profile_user = user_result.scalar_one_or_none()
                if profile_user:
                    profile_user_data = {
                        "id": str(profile_user.id),
                        "email": profile_user.email,
                        "display_name": profile_user.display_name,
                        "profile_picture_url": profile_user.profile_picture_url,
                    }
            except:
                pass
            
            professionals_data.append({
                "id": str(profile.id),
                "slug": profile.slug,
                "full_name": profile.full_name,
                "headline": profile.headline,
                "skills": profile.skills or [],
                "user": profile_user_data,
            })
        professionals = professionals_data
    
    # Get current user (optional)
    user: Optional[User] = None
    user_data = None
    try:
        user = await get_current_user(request, db)
        if user:
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "profile_picture_url": user.profile_picture_url,
            }
    except:
        pass
    
    total_results = total_businesses + total_professionals
    total_pages = (total_results + per_page - 1) // per_page
    
    return render_template(
        "search.html",
        request,
        businesses=businesses,
        professionals=professionals,
        user=user_data,
        query=q or "",
        type=type,
        category=category,
        skill=skill,
        page=page,
        total_pages=total_pages,
        total_businesses=total_businesses,
        total_professionals=total_professionals,
        total_results=total_results
    )

