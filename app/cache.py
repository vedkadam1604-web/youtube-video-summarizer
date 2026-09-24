import time
from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Small in-memory LRU cache with expiry — avoids paying for the same video twice."""

    def __init__(self, max_entries: int, ttl_seconds: int):
        self.max_entries = max_entries
        self.ttl = ttl_seconds
        self._data: OrderedDict[str, tuple[float, T]] = OrderedDict()

    def get(self, key: str) -> T | None:
        item = self._data.get(key)
        if item is None:
            return None
        stored_at, value = item
        if time.monotonic() - stored_at > self.ttl:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: T) -> None:
        self._data[key] = (time.monotonic(), value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)
