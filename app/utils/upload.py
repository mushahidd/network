"""
File upload utilities
"""
from fastapi import UploadFile, HTTPException, status
from PIL import Image
import os
import uuid
from pathlib import Path

from app.config import settings


async def save_uploaded_file(file: UploadFile, folder: str) -> str:
    """
    Save uploaded file and return relative URL.
    
    Args:
        file: FastAPI UploadFile object
        folder: Subfolder in uploads directory (logos, covers, profiles)
        
    Returns:
        Relative URL to saved file
        
    Raises:
        HTTPException: If file is invalid
    """
    # Check if file is actually provided
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided"
        )
    
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if not file_ext or file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Read file content
    content = await file.read()
    
    # Validate file size
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )
    
    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    
    # Create directory if it doesn't exist
    upload_dir = os.path.join(settings.UPLOAD_DIR, folder)
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file
    file_path = os.path.join(upload_dir, unique_filename)
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Resize image if needed
    try:
        image = Image.open(file_path)
        
        # Resize based on folder type
        if folder == "logos":
            # Resize to 400x400 max
            image.thumbnail((400, 400), Image.Resampling.LANCZOS)
        elif folder == "covers":
            # Resize to 1200x400 max
            image.thumbnail((1200, 400), Image.Resampling.LANCZOS)
        elif folder == "profiles":
            # Resize to 400x400 max
            image.thumbnail((400, 400), Image.Resampling.LANCZOS)
        
        # Save resized image
        image.save(file_path, optimize=True, quality=85)
    except Exception as e:
        # If image processing fails, still save the original file
        pass
    
    # Return relative URL
    return f"/static/uploads/{folder}/{unique_filename}"


async def delete_file(file_url: str) -> None:
    """
    Delete file from filesystem.
    
    Args:
        file_url: Relative URL to file (e.g., /static/uploads/logos/file.jpg)
    """
    try:
        # Extract path from URL
        if file_url.startswith("/static/"):
            file_path = file_url.replace("/static/", "app/static/")
            if os.path.exists(file_path):
                os.remove(file_path)
    except Exception:
        # Ignore errors when deleting files
        pass

