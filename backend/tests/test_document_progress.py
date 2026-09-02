import json
import uuid
from unittest.mock import Mock, patch

from redis.exceptions import RedisError

from app.services.document_progress import (
    STREAM_MAX_LENGTH,
    STREAM_TTL_SECONDS,
    document_progress_key,
    publish_document_progress,
    read_document_progress,
    serialize_sse,
)


@patch("app.services.document_progress.get_redis_client")
def test_publish_document_progress_uses_bounded_expiring_stream(mock_get_client):
    client = Mock()
    client.xadd.return_value = "1000-0"
    mock_get_client.return_value = client
    document_id = uuid.uuid4()
    payload = {"stage": "intake_done", "percentage": 70}

    event_id = publish_document_progress(document_id, payload)

    assert event_id == "1000-0"
    client.xadd.assert_called_once_with(
        document_progress_key(document_id),
        {"payload": json.dumps(payload, default=str)},
        maxlen=STREAM_MAX_LENGTH,
        approximate=True,
    )
    client.expire.assert_called_once_with(
        document_progress_key(document_id), STREAM_TTL_SECONDS
    )


@patch("app.services.document_progress.get_redis_client")
def test_publish_document_progress_does_not_fail_pipeline(mock_get_client):
    mock_get_client.side_effect = RedisError("redis unavailable")

    assert publish_document_progress(uuid.uuid4(), {"stage": "init"}) is None


@patch("app.services.document_progress.get_redis_client")
def test_read_document_progress_preserves_stream_order(mock_get_client):
    document_id = uuid.uuid4()
    client = Mock()
    client.xread.return_value = [
        (
            document_progress_key(document_id),
            [
                ("1000-0", {"payload": '{"stage": "init"}'}),
                ("1001-0", {"payload": '{"stage": "completed"}'}),
            ],
        )
    ]
    mock_get_client.return_value = client

    events = read_document_progress(document_id, "999-0", block_ms=25)

    assert events == [
        ("1000-0", {"stage": "init"}),
        ("1001-0", {"stage": "completed"}),
    ]
    client.xread.assert_called_once_with(
        {document_progress_key(document_id): "999-0"},
        count=100,
        block=25,
    )


def test_serialize_sse_includes_redis_stream_id():
    result = serialize_sse({"stage": "completed"}, "1001-0")

    assert result.startswith("id: 1001-0\n")
    assert 'data: {"stage": "completed"}\n\n' in result
