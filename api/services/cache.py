import logging
import time

logger = logging.getLogger(__name__)

cache = {}


def normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def make_key(query: str, role: str) -> str:
    return f"{normalize_query(query)}:{role}"


def set_cache(query: str, role: str, value):
    key = make_key(query, role)
    cache[key] = {"value": value, "time": time.time(), "hits": 0}
    logger.info(f"Cache set for key: {key}")


def get_cache(query: str, role: str, ttl=300):
    key = make_key(query, role)

    item = cache.get(key)

    if not item:
        logger.info(f"Cache miss for key: {key}")
        return None

    age = time.time() - item["time"]

    if age > ttl:
        del cache[key]
        logger.info(f"Cache expired for key: {key}")
        return None

    item["hits"] += 1
    logger.info(f"Cache hit for key: {key}, hits: {item['hits']}")

    return item["value"]
