"""Redis Streams transport for live document-processing progress."""

import json
import logging
import uuid
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

STREAM_MAX_LENGTH = 200
STREAM_TTL_SECONDS = 24 * 60 * 60
STREAM_BLOCK_MS = 15_000


def document_progress_key(document_id: str | uuid.UUID) -> str:
    """Return the isolated Redis Stream key for one document."""
    return f"document-processing:{document_id}"


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """Create the process-wide Redis client used by publishers and observers."""
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def publish_document_progress(
    document_id: str | uuid.UUID,
    payload: dict[str, Any],
) -> str | None:
    """Publish progress without making Redis critical to accounting persistence."""
    try:
        client = get_redis_client()
        key = document_progress_key(document_id)
        event_id = client.xadd(
            key,
            {"payload": json.dumps(payload, default=str)},
            maxlen=STREAM_MAX_LENGTH,
            approximate=True,
        )
        client.expire(key, STREAM_TTL_SECONDS)
        return str(event_id)
    except RedisError as exc:
        logger.warning(
            "Unable to publish document progress document_id=%s: %s",
            document_id,
            exc,
        )
        return None


def read_document_progress(
    document_id: str | uuid.UUID,
    last_event_id: str,
    *,
    block_ms: int = STREAM_BLOCK_MS,
) -> list[tuple[str, dict[str, Any]]]:
    """Read ordered progress events after a Redis Stream ID."""
    streams = get_redis_client().xread(
        {document_progress_key(document_id): last_event_id},
        count=100,
        block=block_ms,
    )
    events: list[tuple[str, dict[str, Any]]] = []
    for _stream_name, entries in streams:
        for event_id, fields in entries:
            payload = json.loads(fields["payload"])
            events.append((str(event_id), payload))
    return events


def serialize_sse(payload: dict[str, Any], event_id: str | None = None) -> str:
    """Serialize one progress payload using the SSE wire format."""
    id_line = f"id: {event_id}\n" if event_id else ""
    return f"{id_line}data: {json.dumps(payload, default=str)}\n\n"
