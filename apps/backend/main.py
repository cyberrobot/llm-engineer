from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from slowapi.middleware import SlowAPIMiddleware

from api.router import api_router
from core.config import get_openai_api_key
from core.exceptions import register_exception_handlers
from core.logging import configure_logging
from infrastructure.database.connection import init_db
from shared.dependencies.rate_limit import limiter


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
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

api_key = get_openai_api_key()
if not api_key:
    raise ValueError("OPENAI_API_KEY is not set in the environment variables.")

client = OpenAI(api_key=api_key)
