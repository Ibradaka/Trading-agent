import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import structlog

from app.services.redis_client import get_redis

router = APIRouter()
logger = structlog.get_logger()


async def _signal_event_generator():
    """Génère les événements SSE depuis Redis pub/sub."""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.psubscribe("signal:*", "price:*", "agent:*")

    try:
        # Envoie un heartbeat toutes les 30s pour maintenir la connexion
        heartbeat_task = asyncio.create_task(_heartbeat_generator())
        async for message in pubsub.listen():
            if message["type"] in ("pmessage", "message"):
                channel = message.get("channel", "")
                data = message.get("data", "")

                event_type = "update"
                if channel.startswith("signal:"):
                    event_type = "signal_updated"
                elif channel.startswith("price:"):
                    event_type = "price_updated"
                elif channel.startswith("agent:"):
                    event_type = "agent_status"

                yield f"event: {event_type}\n"
                yield f"data: {data}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.punsubscribe()
        await pubsub.aclose()


async def _heartbeat_generator():
    """Heartbeat toutes les 30s pour éviter les timeouts nginx."""
    while True:
        await asyncio.sleep(30)


@router.get("/signals")
async def stream_signals():
    """SSE endpoint — le frontend s'abonne ici pour les mises à jour temps réel."""
    return StreamingResponse(
        _signal_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Désactive le buffering Nginx
        },
    )


@router.get("/ping")
async def sse_ping():
    """Test simple SSE — envoie 3 events puis se ferme."""
    async def _ping():
        for i in range(3):
            yield f"data: {json.dumps({'ping': i})}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(_ping(), media_type="text/event-stream")
