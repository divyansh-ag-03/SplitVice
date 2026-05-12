"""
Jinja2 template engine singleton.

Import `templates` and call templates.TemplateResponse(...) in web routes.
Uses the new Starlette signature: TemplateResponse(request, name, context).
"""

from fastapi import Request
from fastapi.templating import Jinja2Templates

_jinja = Jinja2Templates(directory="app/templates")


def render(request: Request, template: str, context: dict | None = None, status_code: int = 200):
    """
    Thin wrapper around Jinja2Templates.TemplateResponse.

    Usage:
        return render(request, "auth/login.html", {"error": "..."})
    """
    ctx = context or {}
    return _jinja.TemplateResponse(request, template, ctx, status_code=status_code)
