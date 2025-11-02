"""
Helper utility functions
"""
import re
from typing import Optional


def generate_slug(text: str) -> str:
    """
    Generate a URL-friendly slug from text.
    
    Args:
        text: The text to convert to a slug
        
    Returns:
        A URL-friendly slug
    """
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)
    # Remove all non-word characters except hyphens
    text = re.sub(r'[^\w\-]', '', text)
    # Replace multiple hyphens with single hyphen
    text = re.sub(r'-+', '-', text)
    # Remove leading/trailing hyphens
    text = text.strip('-')
    return text


def increment_view_count(model_instance) -> None:
    """
    Increment view count for a model instance.
    
    Args:
        model_instance: Model instance with view_count attribute
    """
    if hasattr(model_instance, 'view_count'):
        model_instance.view_count = (model_instance.view_count or 0) + 1

