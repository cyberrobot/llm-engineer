from collections.abc import Iterator
from typing import Any

import redis

from operations.domain.administration import CacheRegionStatistics, OperationsDependencyUnavailable


class RedisCacheRegion:
    """Administer only a registered key namespace; never flush the shared Redis database."""

    def __init__(self, name: str, client: Any, *, key_prefix: str) -> None:
        self.name = name
        self._client = client
        self._key_prefix = key_prefix

    def statistics(self) -> CacheRegionStatistics:
        return CacheRegionStatistics(name=self.name)

    def clear(self) -> None:
        try:
            batch: list[str] = []
            for key in self._keys():
                batch.append(key)
                if len(batch) == 200:
                    self._client.delete(*batch)
                    batch.clear()
            if batch:
                self._client.delete(*batch)
        except redis.RedisError as exc:
            raise OperationsDependencyUnavailable("Cache invalidation failed.") from exc

    def clear_key(self, key: str) -> bool:
        namespaced = key if key.startswith(self._key_prefix) else f"{self._key_prefix}{key}"
        try:
            return bool(self._client.delete(namespaced))
        except redis.RedisError as exc:
            raise OperationsDependencyUnavailable("Cache invalidation failed.") from exc

    def _keys(self) -> Iterator[str]:
        yield from self._client.scan_iter(match=f"{self._key_prefix}*", count=200)
