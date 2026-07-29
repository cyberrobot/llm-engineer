import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from api.openapi import API_CONTRACT_VERSION, create_openapi_schema
from api.router import api_router
from assistant.api.dependencies import get_ai_provider, get_website_loader
from core.config import validate_startup_configuration
from core.exceptions import register_exception_handlers
from core.logging import configure_logging
from infrastructure.database.connection import init_db
from shared.dependencies.rate_limit import limiter


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_startup_configuration()
    if os.getenv("DATABASE_URL"):
        init_db()
    try:
        yield
    finally:
        if get_website_loader.cache_info().currsize:
            loader = get_website_loader()
            close_loader = getattr(loader, "close", None)
            if close_loader is not None:
                close_loader()
            get_website_loader.cache_clear()
        if get_ai_provider.cache_info().currsize:
            provider = get_ai_provider()
            close_provider = getattr(provider, "close", None)
            if close_provider is not None:
                close_provider()
            get_ai_provider.cache_clear()


app = FastAPI(
    title="AI Discovery Assistant API",
    version=API_CONTRACT_VERSION,
    description="Versioned API contracts for the AI Discovery Assistant.",
    lifespan=lifespan,
)
app.openapi = create_openapi_schema(app)  # type: ignore[method-assign]
configure_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://app.redmoorconsulting.co.uk",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.state.limiter = limiter
register_exception_handlers(app)
app.add_middleware(SlowAPIMiddleware)
app.include_router(api_router)
