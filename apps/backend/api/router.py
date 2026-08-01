from fastapi import APIRouter

from admin_auth.routes import router as admin_auth_router
from api.routes.health import router as health_router
from assistant.api.routes import router as assistant_router
from operations.api.router import router as operations_router

api_router = APIRouter()
api_router.include_router(admin_auth_router)
api_router.include_router(health_router)
api_router.include_router(assistant_router)
api_router.include_router(operations_router)
