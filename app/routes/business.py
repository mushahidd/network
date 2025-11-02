"""
Business listing routes
"""
from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import Optional, List
from uuid import UUID

from app.database import get_db
from app.models import User, Business, BusinessCategory, ProfessionalProfile
from app.utils.auth import require_auth, get_current_user
from app.utils.helpers import generate_slug, increment_view_count
from app.utils.upload import save_uploaded_file, delete_file
from jinja2 import Environment, FileSystemLoader
import os
import logging

router = APIRouter()

templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_path))


def render_template(template_name: str, request: Request, **context):
    """Render Jinja2 template"""
    template = jinja_env.get_template(template_name)
    return HTMLResponse(content=template.render(request=request, **context))


@router.get("/businesses", response_class=HTMLResponse)
async def business_directory(
    request: Request,
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """Public business directory"""
    per_page = 20
    offset = (page - 1) * per_page
    
    # Build query
    query = select(Business).where(Business.is_published == True)
    
    # Filter by category
    if category:
        try:
            category_enum = BusinessCategory[category.upper()]
            query = query.where(Business.category == category_enum)
        except KeyError:
            pass
    
    # Search filter
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            Business.business_name.ilike(search_filter) |
            Business.tagline.ilike(search_filter) |
            Business.description.ilike(search_filter)
        )
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
    query = query.order_by(Business.created_at.desc()).limit(per_page).offset(offset)
    result = await db.execute(query)
    businesses_list = result.scalars().all()
    
    # Extract business data to avoid greenlet errors
    businesses_data = []
    for business in businesses_list:
        business_category = business.category  # Extract enum before accessing .value
        businesses_data.append({
            "id": str(business.id),
            "slug": business.slug,
            "business_name": business.business_name,
            "tagline": business.tagline,
            "description": business.description,
            "category": business_category,
            "category_value": business_category.value if business_category else None,
            "logo_url": business.logo_url,
            "cover_image_url": business.cover_image_url,
            "location": business.location,
            "view_count": business.view_count or 0,
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
        "businesses/directory.html",
        request,
        businesses=businesses_data,
        user=user_data,
        category=category,
        search=search,
        page=page,
        total_pages=total_pages,
        total=total
    )


@router.get("/business/{slug}", response_class=HTMLResponse)
async def business_detail(
    request: Request,
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """Individual business profile page"""
    try:
        import logging
        logging.info(f"Business detail request for slug: {slug}")
        
        # Get business
        query = select(Business).where(Business.slug == slug)
        result = await db.execute(query)
        business = result.scalar_one_or_none()
        
        if not business:
            logging.warning(f"Business not found for slug: {slug}")
            raise HTTPException(status_code=404, detail="Business not found")
        
        if not business.is_published:
            logging.warning(f"Business {slug} exists but is not published")
            raise HTTPException(status_code=404, detail="Business not found")
        
        # EXTRACT ALL BUSINESS PROPERTIES IMMEDIATELY to avoid greenlet errors
        business_id = str(business.id)
        business_user_id = str(business.user_id)
        business_category = business.category
        business_slug = business.slug
        business_name = business.business_name
        business_tagline = business.tagline
        business_description = business.description
        business_industry_tags = business.industry_tags or []
        business_logo_url = business.logo_url
        business_cover_image_url = business.cover_image_url
        business_contact_email = business.contact_email
        business_contact_phone = business.contact_phone
        business_website_url = business.website_url
        business_linkedin_url = business.linkedin_url
        business_location = business.location
        business_view_count = business.view_count or 0
        business_created_at = business.created_at
        business_updated_at = business.updated_at
        
        # Increment view count (once per session)
        # TODO: Implement session-based view counting
        try:
            increment_view_count(business)
            await db.commit()
        except Exception as e:
            logging.warning(f"Could not increment view count: {e}")
            await db.rollback()
        
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
                }
        except:
            pass
        
        # Load owner explicitly to avoid relationship access in template
        owner_data = None
        try:
            owner_query = select(User).where(User.id == business_user_id)
            owner_result = await db.execute(owner_query)
            owner = owner_result.scalar_one_or_none()
            if owner:
                owner_id_str = str(owner.id)
                owner_display_name = owner.display_name
                owner_email = owner.email
                owner_profile_picture_url = owner.profile_picture_url
                
                # Check if owner has professional profile
                profile_query = select(ProfessionalProfile).where(ProfessionalProfile.user_id == owner_id_str)
                profile_result = await db.execute(profile_query)
                profile = profile_result.scalar_one_or_none()
                
                profile_slug = None
                if profile:
                    profile_slug = profile.slug
                
                owner_data = {
                    "id": owner_id_str,
                    "display_name": owner_display_name,
                    "email": owner_email,
                    "profile_picture_url": owner_profile_picture_url,
                    "professional_profile": {
                        "slug": profile_slug
                    } if profile_slug else None
                }
        except Exception as e:
            logging.warning(f"Could not load owner data: {e}")
        
        # Extract all business data BEFORE rendering (to avoid greenlet errors)
        # Convert enum to string, extract all needed values
        business_data = {
            "id": business_id,
            "business_name": business_name,
            "slug": business_slug,
            "tagline": business_tagline,
            "description": business_description,
            "category": business_category.value if business_category else None,
            "industry_tags": business_industry_tags,
            "logo_url": business_logo_url,
            "cover_image_url": business_cover_image_url,
            "contact_email": business_contact_email,
            "contact_phone": business_contact_phone,
            "website_url": business_website_url,
            "linkedin_url": business_linkedin_url,
            "location": business_location,
            "view_count": business_view_count,
            "user_id": business_user_id,
            "created_at": business_created_at,
            "updated_at": business_updated_at,
            "owner": owner_data,
        }
        
        # Get related businesses (same category) - use extracted values
        related_businesses_data = []
        try:
            if business_category:
                # Use business_id (already extracted as string) - need to convert back to UUID for query
                from uuid import UUID
                try:
                    business_uuid = UUID(business_id)
                except:
                    business_uuid = None
                
                if business_uuid:
                    related_query = select(Business).where(
                        Business.category == business_category,
                        Business.id != business_uuid,
                        Business.is_published == True
                    ).limit(3)
                    related_result = await db.execute(related_query)
                    related_businesses = related_result.scalars().all()
                else:
                    related_businesses = []
            else:
                related_businesses = []
            
            # Extract data from related businesses - extract all properties before loop ends
            for rb in related_businesses:
                rb_id = str(rb.id)
                rb_slug = rb.slug
                rb_name = rb.business_name
                rb_tagline = rb.tagline
                rb_logo_url = rb.logo_url
                rb_cover_image_url = rb.cover_image_url
                rb_category = rb.category  # Extract enum before accessing .value
                
                related_businesses_data.append({
                    "id": rb_id,
                    "slug": rb_slug,
                    "business_name": rb_name,
                    "tagline": rb_tagline,
                    "logo_url": rb_logo_url,
                    "category": rb_category.value if rb_category else None,
                    "cover_image_url": rb_cover_image_url,
                })
        except Exception as e:
            logging.warning(f"Could not fetch related businesses: {e}")
        
        # Render template with all data extracted (no database objects)
        return render_template(
            "businesses/detail.html",
            request,
            business=business_data,
            user=user_data,
            related_businesses=related_businesses_data
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error displaying business detail: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading business: {str(e)}"
        )


@router.get("/dashboard/business/new", response_class=HTMLResponse)
async def create_business_form(
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Form to create new business"""
    # Extract user data to avoid greenlet errors
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "profile_picture_url": user.profile_picture_url,
    }
    return render_template("businesses/form.html", request, user=user_data, business=None)


@router.post("/dashboard/business")
async def create_business(
    request: Request,
    business_name: str = Form(...),
    tagline: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    contact_email: str = Form(...),
    contact_phone: Optional[str] = Form(None),
    website_url: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    location: str = Form(...),
    industry_tags: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    cover_image: Optional[UploadFile] = File(None),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Create new business"""
    # Validate business name
    if len(business_name) < 3 or len(business_name) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business name must be between 3 and 100 characters"
        )
    
    # Validate tagline
    if len(tagline) > 150:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tagline must be 150 characters or less"
        )
    
    # Validate category
    try:
        category_enum = BusinessCategory[category.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {', '.join([c.value for c in BusinessCategory])}"
        )
    
    # Generate slug
    base_slug = generate_slug(business_name)
    slug = base_slug
    
    # Ensure slug is unique
    counter = 1
    while True:
        existing_query = select(Business).where(Business.slug == slug)
        existing_result = await db.execute(existing_query)
        if existing_result.scalar_one_or_none() is None:
            break
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    # Process industry tags
    tags_list = []
    if industry_tags:
        tags_list = [tag.strip() for tag in industry_tags.split(",") if tag.strip()]
    
    # Handle file uploads (only process if file was actually uploaded)
    logo_url = None
    if logo and logo.filename and logo.filename.strip():
        try:
            logo_url = await save_uploaded_file(logo, "logos")
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error uploading logo: {str(e)}"
            )
    
    cover_image_url = None
    if cover_image and cover_image.filename and cover_image.filename.strip():
        try:
            cover_image_url = await save_uploaded_file(cover_image, "covers")
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error uploading cover image: {str(e)}"
            )
    
    # Create business
    try:
        # Ensure user_id is string for SQLite compatibility
        user_id_str = str(user.id)
        
        business = Business(
            user_id=user_id_str,
            business_name=business_name,
            slug=slug,
            tagline=tagline,
            description=description,
            category=category_enum,
            industry_tags=tags_list if tags_list else None,
            logo_url=logo_url,
            cover_image_url=cover_image_url,
            contact_email=contact_email,
            contact_phone=contact_phone,
            website_url=website_url,
            linkedin_url=linkedin_url,
            location=location,
            is_published=True
        )
        
        db.add(business)
        await db.commit()
        await db.refresh(business)
        
        logging.info(f"Business created successfully: {business_name}, slug: {slug}, id: {business.id}")
        
        return RedirectResponse(url=f"/business/{slug}", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error creating business: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create business: {str(e)}"
        )


@router.get("/dashboard/business/{business_id}/edit", response_class=HTMLResponse)
async def edit_business_form(
    request: Request,
    business_id: str,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Form to edit existing business"""
    import logging
    logging.info(f"Edit business form request for ID: {business_id}")
    
    # SQLite uses string IDs, so compare as strings
    # Also try UUID format for PostgreSQL compatibility
    business_id_str = str(business_id).strip()
    
    # Get business - try string comparison first (for SQLite)
    try:
        # Try string comparison first (SQLite stores UUIDs as strings)
        query = select(Business).where(Business.id == business_id_str)
        result = await db.execute(query)
        business = result.scalar_one_or_none()
        
        # If not found, try UUID comparison (for PostgreSQL)
        if not business:
            try:
                business_uuid = UUID(business_id_str)
                query = select(Business).where(Business.id == business_uuid)
                result = await db.execute(query)
                business = result.scalar_one_or_none()
            except (ValueError, AttributeError):
                pass  # Keep business as None
        
        if not business:
            logging.warning(f"Business not found for ID: {business_id_str}")
            # Try to find by slug as fallback
            query = select(Business).where(Business.slug == business_id_str)
            result = await db.execute(query)
            business = result.scalar_one_or_none()
            if business:
                logging.info(f"Found business by slug: {business.business_name}")
        
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        logging.info(f"Found business: {business.business_name}")
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logging.error(f"Error querying business: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading business: {str(e)}")
    
    # Check ownership (ensure string comparison for SQLite compatibility)
    business_user_id = str(business.user_id)
    user_id_str = str(user.id)
    if business_user_id != user_id_str:
        raise HTTPException(status_code=403, detail="Not authorized to edit this business")
    
    # EXTRACT ALL BUSINESS PROPERTIES IMMEDIATELY to avoid greenlet errors
    business_id_str = str(business.id)
    business_name_val = business.business_name
    business_slug_val = business.slug
    business_tagline_val = business.tagline
    business_description_val = business.description
    business_category_enum = business.category
    business_industry_tags_list = business.industry_tags or []
    business_logo_url_val = business.logo_url
    business_cover_image_url_val = business.cover_image_url
    business_contact_email_val = business.contact_email
    business_contact_phone_val = business.contact_phone
    business_website_url_val = business.website_url
    business_linkedin_url_val = business.linkedin_url
    business_location_val = business.location
    
    # Extract business data to avoid greenlet errors and ensure proper serialization
    business_data = {
        "id": business_id_str,
        "business_name": business_name_val,
        "slug": business_slug_val,
        "tagline": business_tagline_val,
        "description": business_description_val,
        "category": business_category_enum,  # Keep enum for template comparison
        "category_value": business_category_enum.value if business_category_enum else None,  # Extract value safely
        "industry_tags": business_industry_tags_list,
        "logo_url": business_logo_url_val,
        "cover_image_url": business_cover_image_url_val,
        "contact_email": business_contact_email_val,
        "contact_phone": business_contact_phone_val,
        "website_url": business_website_url_val,
        "linkedin_url": business_linkedin_url_val,
        "location": business_location_val,
    }
    
    # Extract user data to avoid greenlet errors
    user_data = {
        "id": user_id_str,
        "email": user.email,
        "display_name": user.display_name,
        "profile_picture_url": user.profile_picture_url,
    }
    
    try:
        return render_template("businesses/form.html", request, user=user_data, business=business_data)
    except Exception as e:
        import logging
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error rendering business edit form: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error loading business edit form: {str(e)}"
        )


@router.post("/dashboard/business/{business_id}")
async def update_business(
    request: Request,
    business_id: str,
    business_name: str = Form(...),
    tagline: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    contact_email: str = Form(...),
    contact_phone: Optional[str] = Form(None),
    website_url: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    location: str = Form(...),
    industry_tags: Optional[str] = Form(None),
    logo: Optional[UploadFile] = File(None),
    cover_image: Optional[UploadFile] = File(None),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Update existing business"""
    import logging
    logging.info(f"Update business request for ID: {business_id}")
    
    # SQLite uses string IDs, so compare as strings first
    business_id_str = str(business_id).strip()
    
    # Get business - try string comparison first (for SQLite)
    business = None
    try:
        # Try string comparison first (SQLite stores UUIDs as strings)
        query = select(Business).where(Business.id == business_id_str)
        result = await db.execute(query)
        business = result.scalar_one_or_none()
        
        # If not found, try UUID comparison (for PostgreSQL)
        if not business:
            try:
                business_uuid = UUID(business_id_str)
                query = select(Business).where(Business.id == business_uuid)
                result = await db.execute(query)
                business = result.scalar_one_or_none()
            except (ValueError, AttributeError):
                pass
        
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        logging.info(f"Found business to update: {business.business_name}")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error querying business: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading business: {str(e)}")
    
    # Check ownership (ensure string comparison for SQLite compatibility)
    business_user_id = str(business.user_id)
    user_id_str = str(user.id)
    if business_user_id != user_id_str:
        raise HTTPException(status_code=403, detail="Not authorized to edit this business")
    
    # Validate inputs
    if len(business_name) < 3 or len(business_name) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business name must be between 3 and 100 characters"
        )
    
    try:
        category_enum = BusinessCategory[category.upper()]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category"
        )
    
    # Extract current business name and ID immediately to avoid greenlet errors
    current_business_name = business.business_name
    current_business_id = str(business.id)
    
    # Update slug if name changed
    if current_business_name != business_name:
        base_slug = generate_slug(business_name)
        slug = base_slug
        counter = 1
        while True:
            # Use extracted ID for comparison
            existing_query = select(Business).where(
                Business.slug == slug,
                Business.id != current_business_id
            )
            existing_result = await db.execute(existing_query)
            if existing_result.scalar_one_or_none() is None:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        business.slug = slug
    
    # Process industry tags
    tags_list = []
    if industry_tags:
        tags_list = [tag.strip() for tag in industry_tags.split(",") if tag.strip()]
    
    # Handle file uploads (only process if file was actually uploaded)
    if logo and logo.filename and logo.filename.strip():
        try:
            # Delete old logo if exists
            if business.logo_url:
                await delete_file(business.logo_url)
            business.logo_url = await save_uploaded_file(logo, "logos")
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error uploading logo: {str(e)}"
            )
    
    if cover_image and cover_image.filename and cover_image.filename.strip():
        try:
            # Delete old cover if exists
            if business.cover_image_url:
                await delete_file(business.cover_image_url)
            business.cover_image_url = await save_uploaded_file(cover_image, "covers")
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error uploading cover image: {str(e)}"
            )
    
    # Extract current slug before updating (in case slug changed)
    current_slug = business.slug
    
    # Update business
    business.business_name = business_name
    business.tagline = tagline
    business.description = description
    business.category = category_enum
    business.industry_tags = tags_list if tags_list else None
    business.contact_email = contact_email
    business.contact_phone = contact_phone
    business.website_url = website_url
    business.linkedin_url = linkedin_url
    business.location = location
    
    try:
        await db.commit()
        await db.refresh(business)
        
        # Use updated slug if it changed, otherwise use current
        final_slug = business.slug if business.slug else current_slug
        logging.info(f"Business updated successfully: {business_name}, redirecting to slug: {final_slug}")
        
        return RedirectResponse(url=f"/business/{final_slug}", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        await db.rollback()
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error updating business: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update business: {str(e)}"
        )


@router.post("/dashboard/business/{business_id}/delete")
async def delete_business(
    request: Request,
    business_id: str,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """Delete business"""
    import logging
    logging.info(f"Delete business request for ID: {business_id}")
    
    # SQLite uses string IDs, so compare as strings first
    business_id_str = str(business_id).strip()
    
    # Get business - try string comparison first (for SQLite)
    business = None
    try:
        # Try string comparison first (SQLite stores UUIDs as strings)
        query = select(Business).where(Business.id == business_id_str)
        result = await db.execute(query)
        business = result.scalar_one_or_none()
        
        # If not found, try UUID comparison (for PostgreSQL)
        if not business:
            try:
                business_uuid = UUID(business_id_str)
                query = select(Business).where(Business.id == business_uuid)
                result = await db.execute(query)
                business = result.scalar_one_or_none()
            except (ValueError, AttributeError):
                pass
        
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        logging.info(f"Found business to delete: {business.business_name}")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error querying business: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading business: {str(e)}")
    
    # Check ownership (ensure string comparison for SQLite compatibility)
    business_user_id = str(business.user_id)
    user_id_str = str(user.id)
    if business_user_id != user_id_str:
        raise HTTPException(status_code=403, detail="Not authorized to delete this business")
    
    # Extract file URLs before deletion
    logo_url_to_delete = business.logo_url
    cover_url_to_delete = business.cover_image_url
    business_id_for_delete = str(business.id)
    
    # Delete associated images
    if logo_url_to_delete:
        try:
            await delete_file(logo_url_to_delete)
        except Exception as e:
            logging.warning(f"Could not delete logo file: {e}")
    
    if cover_url_to_delete:
        try:
            await delete_file(cover_url_to_delete)
        except Exception as e:
            logging.warning(f"Could not delete cover image file: {e}")
    
    # Delete business (SQLAlchemy 2.0 async pattern)
    try:
        stmt = delete(Business).where(Business.id == business_id_for_delete)
        await db.execute(stmt)
        await db.commit()
        logging.info(f"Business deleted successfully: {business_id_str}")
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception as e:
        await db.rollback()
        import traceback
        error_details = traceback.format_exc()
        logging.error(f"Error deleting business: {e}\n{error_details}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete business: {str(e)}"
        )

