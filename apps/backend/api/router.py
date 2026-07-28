from fastapi import APIRouter

from api.routes.health import router as health_router
from assistant.api.routes import router as assistant_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(assistant_router)
