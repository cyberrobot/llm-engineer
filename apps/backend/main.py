import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.middleware import SlowAPIMiddleware

from admin_auth.dependencies import (
    get_administrator_auth_repository,
    get_administrator_password_service,
)
from admin_auth.service import AdministratorAuthenticationService
from api.openapi import API_CONTRACT_VERSION, create_openapi_schema
from api.router import api_router
from assistant.api.dependencies import get_ai_provider, get_website_loader
from core.config import get_admin_authentication_settings, validate_startup_configuration
from core.correlation import RequestCorrelationMiddleware
from core.exceptions import register_exception_handlers
from core.logging import configure_logging
from infrastructure.database.connection import init_db
from shared.dependencies.rate_limit import limiter


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_startup_configuration()
    if os.getenv("DATABASE_URL"):
        init_db()
        admin_settings = get_admin_authentication_settings()
        admin_repository = get_administrator_auth_repository()
        if admin_settings.bootstrap_email and admin_settings.bootstrap_password:
            AdministratorAuthenticationService(
                admin_repository,
                get_administrator_password_service(),
                session_ttl_seconds=admin_settings.session_ttl_seconds,
                login_max_failures=admin_settings.login_max_failures,
                login_lockout_seconds=admin_settings.login_lockout_seconds,
            ).bootstrap(admin_settings.bootstrap_email, admin_settings.bootstrap_password)
        elif os.getenv("APP_ENV", "development").strip().lower() == "production":
            if not admin_repository.has_any_administrator():
                raise ValueError(
                    "Production requires bootstrap credentials when no administrator exists"
                )
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
    allow_origins=list(get_admin_authentication_settings().trusted_origins),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(RequestCorrelationMiddleware)

app.state.limiter = limiter
register_exception_handlers(app)
app.add_middleware(SlowAPIMiddleware)
app.include_router(api_router)
