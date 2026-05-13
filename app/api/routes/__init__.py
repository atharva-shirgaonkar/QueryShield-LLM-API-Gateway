"""Route modules for the QueryShield API."""

from app.api.routes.auth import router as auth_router
from app.api.routes.query import router as query_router

__all__ = ["auth_router", "query_router"]
