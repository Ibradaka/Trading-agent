import json
from typing import Any, Optional
import redis.asyncio as redis
import structlog

from app.config import settings

logger = structlog.get_logger()
_client: Optional[redis.Redis] = None


async def init_redis() -> None:
    global _client
    _client = redis.from_url(settings.redis_url_with_auth, decode_responses=True)
    await _client.ping()
    logger.info("Redis connection established")


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        logger.info("Redis connection closed")


def get_redis() -> redis.Redis:
    if _client is None:
        raise RuntimeError("Redis not initialized")
    return _client


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    await get_redis().setex(key, ttl_seconds, json.dumps(value))


async def cache_get(key: str) -> Optional[Any]:
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None


async def cache_delete(key: str) -> None:
    await get_redis().delete(key)


async def publish(channel: str, message: Any) -> None:
    await get_redis().publish(channel, json.dumps(message))


async def subscribe(channel: str) -> redis.client.PubSub:
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel)
    return pubsub
