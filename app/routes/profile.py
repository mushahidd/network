"""
Professional profile routes
"""
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models import User, ProfessionalProfile, AvailabilityStatus
from app.utils.auth import require_auth, get_current_user
from app.utils.helpers import generate_slug, increment_view_count
from app.utils.upload import save_uploaded_file, delete_file
from jinja2 import Environment, FileSystemLoader
import os

router = APIRouter()

templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_path))


def render_template(template_name: str, request: Request, **context):
    """Render Jinja2 template"""
    template = jinja_env.get_template(template_name)
    return HTMLResponse(content=template.render(request=request, **context))


@router.get("/professionals", response_class=HTMLResponse)
async def professional_directory(
    request: Request,
    skill: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """Public professional directory"""
    per_page = 20
    offset = (page - 1) * per_page
    
    # Build query
    query = select(ProfessionalProfile).where(ProfessionalProfile.is_published == True)
    
    # Filter by skill
    if skill:
        query = query.where(ProfessionalProfile.skills.contains([skill]))
    
    # Search filter
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            ProfessionalProfile.full_name.ilike(search_filter) |
            ProfessionalProfile.headline.ilike(search_filter) |
            ProfessionalProfile.bio.ilike(search_filter)
        )
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
    query = query.order_by(ProfessionalProfile.created_at.desc()).limit(per_page).offset(offset)
    result = await db.execute(query)
    professionals_list = result.scalars().all()
    
    # Extract professional data to avoid greenlet errors
    professionals_data = []
    for profile in professionals_list:
        # Get user data for this profile
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
            "bio": profile.bio,
            "skills": profile.skills or [],
            "user": profile_user_data,
        })
    
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
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template(
        "profiles/directory.html",
        request,
        professionals=professionals_data,
        user=user_data,
        skill=skill,
        search=search,
        page=page,
        total_pages=total_pages,
        total=total
    )


@router.get("/profile/{slug}", response_class=HTMLResponse)
async def profile_detail(
    request: Request,
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """Individual professional profile page"""
    try:
        # Get profile
        query = select(ProfessionalProfile).where(ProfessionalProfile.slug == slug)
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        if not profile.is_published:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        # Increment view count
        increment_view_count(profile)
        await db.commit()
        
        # Get current user (optional)
        user: Optional[User] = None
        try:
            user = await get_current_user(request, db)
        except:
            pass
        
        # Get profile owner (user) explicitly to avoid relationship access
        user_id_str = str(profile.user_id)
        owner_data = None
        try:
            owner_query = select(User).where(User.id == user_id_str)
            owner_result = await db.execute(owner_query)
            owner = owner_result.scalar_one_or_none()
            if owner:
                owner_data = {
                    "id": str(owner.id),
                    "email": owner.email,
                    "display_name": owner.display_name,
                    "profile_picture_url": owner.profile_picture_url,
                }
        except Exception as e:
            logging.warning(f"Could not load owner data: {e}")
        
        # Extract availability status enum BEFORE any async operations
        availability_status = profile.availability_status
        
        # Extract all profile data BEFORE rendering (to avoid greenlet errors)
        profile_data = {
            "id": str(profile.id),
            "full_name": profile.full_name,
            "slug": profile.slug,
            "headline": profile.headline,
            "bio": profile.bio,
            "profile_summary": profile.profile_summary,
            "skills": profile.skills or [],
            "linkedin_url": profile.linkedin_url,
            "portfolio_url": profile.portfolio_url,
            "how_i_can_help": profile.how_i_can_help,
            "availability_status": availability_status,  # Keep enum for template .value access
            "availability_status_value": availability_status.value if availability_status else None,
            "consent_show_contact": profile.consent_show_contact,
            "consent_show_linkedin": profile.consent_show_linkedin,
            "view_count": profile.view_count or 0,
            "user_id": str(profile.user_id),
            "user": owner_data,  # Add user data to profile
        }
        
        # Extract user data if logged in
        user_data = None
        if user:
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
            }
        
        return render_template(
            "profiles/detail.html",
            request,
            profile=profile_data,
            user=user_data
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        import logging
        error_details = traceback.format_exc()
        logging.error(f"Error displaying profile detail: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading profile: {str(e)}"
        )


@router.get("/dashboard/profile/edit", response_class=HTMLResponse)
async def edit_profile_form(
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Form to create or edit professional profile (one-to-one with user)"""
    # Get existing profile if it exists (ensure string comparison for SQLite)
    user_id_str = str(user.id)
    query = select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id_str)
    result = await db.execute(query)
    profile_obj = result.scalar_one_or_none()
    
    # Extract profile data to avoid greenlet errors and ensure proper serialization
    profile_data = None
    if profile_obj:
        # Extract ALL properties immediately to avoid greenlet errors
        profile_id = str(profile_obj.id)
        profile_full_name = profile_obj.full_name
        profile_slug = profile_obj.slug
        profile_headline = profile_obj.headline
        profile_bio = profile_obj.bio
        profile_summary = profile_obj.profile_summary
        profile_skills = profile_obj.skills or []
        profile_linkedin_url = profile_obj.linkedin_url
        profile_portfolio_url = profile_obj.portfolio_url
        profile_how_i_can_help = profile_obj.how_i_can_help
        availability_status_enum = profile_obj.availability_status
        profile_consent_show_contact = profile_obj.consent_show_contact
        profile_consent_show_linkedin = profile_obj.consent_show_linkedin
        
        profile_data = {
            "id": profile_id,
            "full_name": profile_full_name,
            "slug": profile_slug,
            "headline": profile_headline,
            "bio": profile_bio,
            "profile_summary": profile_summary,
            "skills": profile_skills,
            "linkedin_url": profile_linkedin_url,
            "portfolio_url": profile_portfolio_url,
            "how_i_can_help": profile_how_i_can_help,
            "availability_status": availability_status_enum,  # Keep enum for template comparison
            "availability_status_value": availability_status_enum.value if availability_status_enum else None,  # Extract value safely
            "consent_show_contact": profile_consent_show_contact,
            "consent_show_linkedin": profile_consent_show_linkedin,
        }
    
    # Extract user data to avoid greenlet errors
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "profile_picture_url": user.profile_picture_url,
    }
    
    try:
        return render_template("profiles/form.html", request, user=user_data, profile=profile_data)
    except Exception as e:
        import logging
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error rendering profile edit form: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading profile edit form: {str(e)}"
        )


@router.post("/dashboard/profile")
async def create_or_update_profile(
    request: Request,
    full_name: str = Form(...),
    headline: str = Form(...),
    bio: str = Form(...),
    profile_summary: Optional[str] = Form(None),
    linkedin_url: str = Form(...),
    portfolio_url: Optional[str] = Form(None),
    how_i_can_help: Optional[str] = Form(None),
    skills: Optional[str] = Form(None),
    availability_status: str = Form(...),
    consent_show_contact: bool = Form(False),
    consent_show_linkedin: bool = Form(True),
    profile_picture: Optional[UploadFile] = File(None),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Create or update professional profile"""
    # Validate inputs
    if len(full_name) < 2 or len(full_name) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Full name must be between 2 and 100 characters"
        )
    
    if len(headline) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Headline must be 100 characters or less"
        )
    
    if len(bio) > 300:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bio must be 300 characters or less"
        )
    
    # Validate availability status
    try:
        availability_enum = AvailabilityStatus[availability_status.upper().replace(" ", "_")]
    except KeyError:
        availability_enum = AvailabilityStatus.AVAILABLE
    
    # Get existing profile if it exists (ensure string comparison for SQLite)
    user_id_str = str(user.id)
    query = select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id_str)
    result = await db.execute(query)
    profile = result.scalar_one_or_none()
    
    # Process skills
    skills_list = []
    if skills:
        skills_list = [skill.strip() for skill in skills.split(",") if skill.strip()]
        if len(skills_list) > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 20 skills allowed"
            )
    
    if not skills_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one skill is required"
        )
    
    # Generate slug
    base_slug = generate_slug(full_name)
    slug = base_slug
    
    # Ensure slug is unique (if creating new or name changed)
    if not profile or profile.full_name != full_name:
        counter = 1
        while True:
            existing_query = select(ProfessionalProfile).where(ProfessionalProfile.slug == slug)
            if profile:
                existing_query = existing_query.where(ProfessionalProfile.id != profile.id)
            existing_result = await db.execute(existing_query)
            if existing_result.scalar_one_or_none() is None:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
    
    # Handle file upload (only process if file was actually uploaded)
    profile_picture_url = None
    if profile_picture and profile_picture.filename and profile_picture.filename.strip():
        try:
            # Delete old picture if exists (use user object directly, not profile.user relationship)
            if user.profile_picture_url and "/uploads/" in user.profile_picture_url:
                await delete_file(user.profile_picture_url)
            profile_picture_url = await save_uploaded_file(profile_picture, "profiles")
            # Update user's profile picture
            user.profile_picture_url = profile_picture_url
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error uploading profile picture: {str(e)}"
            )
    elif user.profile_picture_url and not profile:
        profile_picture_url = user.profile_picture_url
    
    if profile:
        # Update existing profile
        profile.full_name = full_name
        profile.slug = slug
        profile.headline = headline
        profile.bio = bio
        profile.profile_summary = profile_summary
        profile.skills = skills_list
        profile.linkedin_url = linkedin_url
        profile.portfolio_url = portfolio_url
        profile.how_i_can_help = how_i_can_help
        profile.availability_status = availability_enum
        profile.consent_show_contact = consent_show_contact
        profile.consent_show_linkedin = consent_show_linkedin
        if profile_picture_url:
            # Update user's profile picture directly
            user.profile_picture_url = profile_picture_url
    else:
        # Create new profile (ensure user_id is string for SQLite compatibility)
        profile = ProfessionalProfile(
            user_id=user_id_str,
            full_name=full_name,
            slug=slug,
            headline=headline,
            bio=bio,
            profile_summary=profile_summary,
            skills=skills_list,
            linkedin_url=linkedin_url,
            portfolio_url=portfolio_url,
            how_i_can_help=how_i_can_help,
            availability_status=availability_enum,
            consent_show_contact=consent_show_contact,
            consent_show_linkedin=consent_show_linkedin,
            is_published=True
        )
        if profile_picture_url:
            user.profile_picture_url = profile_picture_url
        db.add(profile)
    
    await db.commit()
    await db.refresh(profile)
    
    return RedirectResponse(url=f"/profile/{slug}", status_code=status.HTTP_302_FOUND)


@router.post("/dashboard/profile/delete")
async def delete_profile(
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Delete professional profile"""
    try:
        import logging
        # Ensure user_id is string for SQLite compatibility
        user_id_str = str(user.id)
        
        # Get profile
        query = select(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id_str)
        result = await db.execute(query)
        profile = result.scalar_one_or_none()
        
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        # Extract profile ID immediately to avoid greenlet errors
        profile_id_for_delete = str(profile.id)
        profile_slug = profile.slug  # For logging
        
        # Delete associated profile picture if exists (optional cleanup)
        # Note: We don't delete user's profile picture as it might be from OAuth
        # Only delete uploaded files if specifically stored for the profile
        
        # Delete profile (SQLAlchemy 2.0 async pattern)
        stmt = delete(ProfessionalProfile).where(ProfessionalProfile.id == profile_id_for_delete)
        await db.execute(stmt)
        await db.commit()
        
        logging.info(f"Profile deleted successfully for user: {user.email}, profile_id: {profile_id_for_delete}, slug: {profile_slug}")
        
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error deleting profile: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete profile: {str(e)}"
        )

