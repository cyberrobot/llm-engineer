import logging

logger = logging.getLogger(__name__)


def close_cached_dependency(factory, resource_name: str) -> None:
    """Close one cached resource without preventing cleanup of subsequent resources."""
    if not factory.cache_info().currsize:
        return
    try:
        resource = factory()
        close_resource = getattr(resource, "close", None)
        if close_resource is not None:
            close_resource()
    except Exception:
        logger.exception(
            "application_resource_cleanup_failed",
            extra={"reason": resource_name},
        )
    finally:
        factory.cache_clear()
