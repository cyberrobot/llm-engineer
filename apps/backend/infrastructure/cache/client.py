import json
import logging
from typing import Any, Dict, Union, cast

import redis

from core.config import REDIS_URL

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

logger = logging.getLogger(__name__)

logger.info("Redis client initialised url: {REDIS_URL}")


def normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def make_key(query: str, role: str) -> str:
    return f"rag:{normalize_query(query)}:{role}"


def set_cache(query: str, role: str, value: dict[str, Any], ttl: int = 300) -> None:
    key = make_key(query, role)

    try:
        redis_client.setex(key, ttl, json.dumps(value))
        logger.info(f"Cache set for key: {key}, ttl: {ttl} seconds")

    except redis.RedisError as e:
        logger.error(f"Redis error while setting cache for key {key}: {e}")
        return None


def get_cache(query: str, role: str) -> Union[Dict[str, Any], None]:
    key = make_key(query, role)

    try:
        raw = redis_client.get(key)

        if raw is None:
            logger.info(f"Cache miss for key: {key}")
            return None

        logger.info(f"Cache hit for key: {key}")

        return json.loads(cast(str, raw))

    except redis.RedisError as e:
        logger.error(f"Redis error for key {key}: {e}")
        return None
