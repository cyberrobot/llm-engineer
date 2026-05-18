import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.core.rate_limit import limiter, rate_limit_handler
from api.db.database import init_db
from api.routes import audit, ingest, rag

load_dotenv()

init_db()
app = FastAPI()
logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://caring-appreciation-production-5a11.up.railway.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    rate_limit_handler,
)

app.add_middleware(SlowAPIMiddleware)

app.include_router(ingest.router)
app.include_router(rag.router)
app.include_router(audit.router)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY is not set in the environment variables.")

client = OpenAI(api_key=api_key)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health_check():
    return {"status": "healthy"}
