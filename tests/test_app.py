from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import main
from app.cache import TTLCache
from app.config import Settings, get_settings
from app.models import Chapter, ChunkNotes, KeyPoint, LLMSummary
from app.summarizer import Summarizer, chunk_segments
from app.transcript import (
    Segment,
    Transcript,
    TranscriptError,
    extract_video_id,
    format_timestamp,
    to_prompt_text,
)

VID = "dQw4w9WgXcQ"


# ---------- URL parsing ----------


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}&t=42s&list=abc",
        f"youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}?si=xyz",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube.com/live/{VID}",
        f"https://music.youtube.com/watch?v={VID}",
        VID,
    ],
)
def test_extract_video_id(url):
    assert extract_video_id(url) == VID


@pytest.mark.parametrize("url", ["", "https://vimeo.com/123", "https://youtube.com/watch?v=short", "hello"])
def test_extract_video_id_invalid(url):
    with pytest.raises(TranscriptError):
        extract_video_id(url)


def test_format_timestamp():
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(75.9) == "1:15"
    assert format_timestamp(3725) == "1:02:05"


def test_to_prompt_text_groups_segments():
    segs = [Segment(i * 5, f"w{i}") for i in range(10)]
    text = to_prompt_text(segs, block_seconds=20)
    assert text.splitlines()[0] == "[0s] w0 w1 w2 w3 w4"
    assert text.splitlines()[1].startswith("[25s]")


def test_chunk_segments():
    segs = [Segment(i, "x" * 10) for i in range(100)]
    chunks = chunk_segments(segs, 100)
    assert sum(len(c) for c in chunks) == 100
    assert all(len(c) <= 10 for c in chunks)


def test_ttl_cache_evicts_lru():
    c = TTLCache(max_entries=2, ttl_seconds=60)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")
    c.set("c", 3)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3


# ---------- Summarizer (OpenAI mocked) ----------


def fake_summary() -> LLMSummary:
    return LLMSummary(
        tldr="A short video.",
        summary="It covers things.",
        key_points=[KeyPoint(point="Late point", timestamp_seconds=9999), KeyPoint(point="Early", timestamp_seconds=10)],
        chapters=[Chapter(title="Intro", start_seconds=0, summary="Hello.")],
        topics=["testing"],
    )


def mock_client(*outputs):
    client = SimpleNamespace(responses=SimpleNamespace())
    client.responses.parse = AsyncMock(side_effect=[SimpleNamespace(output_parsed=o) for o in outputs])
    return client


async def test_summarizer_single_pass():
    client = mock_client(fake_summary())
    s = Summarizer(client, "m", chunk_threshold=10_000, chunk_size=1_000)
    out = await s.summarize([Segment(0, "hello"), Segment(5, "world")], title="T")
    assert out.tldr == "A short video."
    assert client.responses.parse.await_count == 1


async def test_summarizer_map_reduce_for_long_transcripts():
    segs = [Segment(i * 5, "word " * 40) for i in range(60)]
    n_chunks = len(chunk_segments(segs, 2_000))
    notes = [ChunkNotes(notes=[KeyPoint(point="n", timestamp_seconds=0)]) for _ in range(n_chunks)]
    client = mock_client(*notes, fake_summary())
    s = Summarizer(client, "m", chunk_threshold=1_000, chunk_size=2_000)
    await s.summarize(segs)
    assert n_chunks > 1
    assert client.responses.parse.await_count == n_chunks + 1


# ---------- API ----------


@pytest.fixture
def client():
    main.cache = TTLCache(10, 60)
    main.app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="test", openai_model="test-model")
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def patch_pipeline():
    transcript = Transcript(VID, [Segment(0, "hi"), Segment(10, "there"), Segment(120, "bye")], "en", True)
    return (
        patch.object(main, "fetch_transcript", return_value=transcript),
        patch.object(main, "fetch_metadata", AsyncMock(return_value={"title": "Vid", "channel": "Ch", "thumbnail_url": None})),
        patch.object(Summarizer, "summarize", AsyncMock(return_value=fake_summary())),
    )


def test_summarize_endpoint(client):
    p1, p2, p3 = patch_pipeline()
    with p1, p2, p3 as summarize:
        r = client.post("/api/summarize", json={"url": f"https://youtu.be/{VID}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["video"]["title"] == "Vid"
        # sorted chronologically, and the hallucinated timestamp is clamped to the video length
        assert [k["timestamp_seconds"] for k in body["key_points"]] == [10, 120]
        assert body["key_points"][1]["link"].endswith(f"v={VID}&t=120s")
        assert body["key_points"][0]["timestamp"] == "0:10"
        assert body["cached"] is False

        r2 = client.post("/api/summarize", json={"url": VID})
        assert r2.json()["cached"] is True
        assert summarize.await_count == 1


def test_summarize_invalid_url(client):
    r = client.post("/api/summarize", json={"url": "https://vimeo.com/1"})
    assert r.status_code == 422


def test_summarize_no_captions(client):
    with patch.object(main, "fetch_transcript", side_effect=TranscriptError("Captions are disabled", 404)):
        r = client.post("/api/summarize", json={"url": VID})
    assert r.status_code == 404
    assert "Captions" in r.json()["detail"]


def test_missing_api_key():
    main.app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key="")
    r = TestClient(main.app).post("/api/summarize", json={"url": VID})
    main.app.dependency_overrides.clear()
    assert r.status_code == 500


def test_index_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"


def test_network_error_becomes_502():
    import requests

    from app import transcript as t

    with patch.object(t.YouTubeTranscriptApi, "list", side_effect=requests.ConnectionError("down")):
        with pytest.raises(TranscriptError) as exc:
            t.fetch_transcript(VID)
    assert exc.value.status_code == 502
