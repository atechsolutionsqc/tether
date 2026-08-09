import os
import threading
import time
from typing import Dict, Tuple

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - fallback path when redis isn't installed
    redis = None


_REDIS_URL = os.environ.get("RATE_LIMIT_REDIS_URL", "").strip()
_redis_client = None
if redis and _REDIS_URL:
    try:
        _redis_client = redis.from_url(_REDIS_URL, decode_responses=True)
        _redis_client.ping()
    except Exception:
        _redis_client = None


# In-memory fallback keeps local/dev workable if Redis is unavailable.
_mem_lock = threading.Lock()
_mem_store: Dict[str, Tuple[int, float]] = {}


def _key(bucket: str, subject: str) -> str:
    return f"rl:{bucket}:{subject}"


def _mem_now() -> float:
    return time.time()


def _mem_get_count(key: str) -> int:
    now = _mem_now()
    with _mem_lock:
        rec = _mem_store.get(key)
        if not rec:
            return 0
        count, expiry = rec
        if expiry <= now:
            _mem_store.pop(key, None)
            return 0
        return count


def _mem_incr(key: str, window_sec: int) -> int:
    now = _mem_now()
    expiry = now + window_sec
    with _mem_lock:
        rec = _mem_store.get(key)
        if not rec or rec[1] <= now:
            _mem_store[key] = (1, expiry)
            return 1
        count, old_expiry = rec
        _mem_store[key] = (count + 1, old_expiry)
        return count + 1


def _mem_clear(key: str) -> None:
    with _mem_lock:
        _mem_store.pop(key, None)


def is_limited(bucket: str, subject: str, limit: int) -> bool:
    key = _key(bucket, subject)
    if _redis_client is not None:
        try:
            raw = _redis_client.get(key)
            return int(raw or 0) >= limit
        except Exception:
            pass
    return _mem_get_count(key) >= limit


# Atomic increment-and-expire: sets TTL only on first creation so the window
# is fixed (not sliding). Using a Lua script keeps both operations in one
# round-trip and prevents the TOCTOU gap between INCR and EXPIRE.
_LUA_CONSUME = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def consume(bucket: str, subject: str, limit: int, window_sec: int) -> bool:
    """Record one attempt and return True when still under the limit."""
    key = _key(bucket, subject)
    if _redis_client is not None:
        try:
            count = _redis_client.eval(_LUA_CONSUME, 1, key, window_sec)
            return int(count) <= limit
        except Exception:
            pass
    return _mem_incr(key, window_sec) <= limit


def clear(bucket: str, subject: str) -> None:
    key = _key(bucket, subject)
    if _redis_client is not None:
        try:
            _redis_client.delete(key)
            return
        except Exception:
            pass
    _mem_clear(key)
