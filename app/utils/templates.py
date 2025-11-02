"""
Template rendering utilities
"""
from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
import os


def create_template_env():
    """Create Jinja2 environment for templates"""
    templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
    return Environment(loader=FileSystemLoader(templates_path))


def render_template(template_name: str, request: Request, **context):
    """
    Render Jinja2 template with automatic user injection.
    
    Args:
        template_name: Name of template file
        request: FastAPI request object
        **context: Additional context variables
    
    Returns:
        HTMLResponse with rendered template
    """
    # Get template environment
    templates_path = os.path.join(os.path.dirname(__file__), "..", "templates")
    jinja_env = Environment(loader=FileSystemLoader(templates_path))
    
    # Automatically inject user from request.state if available
    if not context.get('user') and hasattr(request.state, 'user_data'):
        context['user'] = request.state.user_data
    
    # Render template
    template = jinja_env.get_template(template_name)
    return HTMLResponse(content=template.render(request=request, **context))
