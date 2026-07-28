from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import DISABLE_RATE_LIMITS, REDIS_URL

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=None if DISABLE_RATE_LIMITS else REDIS_URL,
    enabled=not DISABLE_RATE_LIMITS,
)
