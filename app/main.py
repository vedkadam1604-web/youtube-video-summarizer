import asyncio
import logging
from pathlib import Path

import openai
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cache import TTLCache
from .config import Settings, get_settings
from .models import (
    LLMSummary,
    SummarizeRequest,
    SummarizeResponse,
    TimestampedChapter,
    TimestampedKeyPoint,
    VideoMeta,
)
from .summarizer import Summarizer
from .transcript import (
    Transcript,
    TranscriptError,
    extract_video_id,
    fetch_metadata,
    fetch_transcript,
    format_timestamp,
)

logger = logging.getLogger("yt_summarizer")
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="YouTube Video Summarizer",
    description="Paste a YouTube URL, get a structured summary with key points and timestamps.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

settings = get_settings()
cache: TTLCache[SummarizeResponse] = TTLCache(settings.cache_max_entries, settings.cache_ttl_seconds)


def get_summarizer(settings: Settings = Depends(get_settings)) -> Summarizer:
    if not settings.openai_api_key:
        raise HTTPException(500, "OPENAI_API_KEY is not configured on the server.")
    return Summarizer(
        client=openai.AsyncOpenAI(api_key=settings.openai_api_key),
        model=settings.openai_model,
        chunk_threshold=settings.chunk_threshold_chars,
        chunk_size=settings.chunk_size_chars,
    )


def build_response(transcript: Transcript, meta: dict, llm: LLMSummary, model: str) -> SummarizeResponse:
    vid = transcript.video_id
    duration = transcript.duration_seconds

    def clamp(t: int) -> int:  # guard against hallucinated timestamps past the end
        return max(0, min(int(t), duration))

    def link(t: int) -> str:
        return f"https://www.youtube.com/watch?v={vid}&t={t}s"

    key_points = sorted(
        (
            TimestampedKeyPoint(
                point=kp.point,
                timestamp_seconds=(t := clamp(kp.timestamp_seconds)),
                timestamp=format_timestamp(t),
                link=link(t),
            )
            for kp in llm.key_points
        ),
        key=lambda k: k.timestamp_seconds,
    )
    chapters = sorted(
        (
            TimestampedChapter(
                title=ch.title,
                start_seconds=(t := clamp(ch.start_seconds)),
                summary=ch.summary,
                timestamp=format_timestamp(t),
                link=link(t),
            )
            for ch in llm.chapters
        ),
        key=lambda c: c.start_seconds,
    )
    return SummarizeResponse(
        video=VideoMeta(
            video_id=vid,
            url=f"https://www.youtube.com/watch?v={vid}",
            duration_seconds=duration,
            transcript_language=transcript.language,
            transcript_is_generated=transcript.is_generated,
            **meta,
        ),
        tldr=llm.tldr,
        summary=llm.summary,
        key_points=key_points,
        chapters=chapters,
        topics=llm.topics,
        model=model,
    )


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "cached_summaries": len(cache)}


@app.post("/api/summarize", response_model=SummarizeResponse)
async def summarize(
    req: SummarizeRequest,
    summarizer: Summarizer = Depends(get_summarizer),
    settings: Settings = Depends(get_settings),
) -> SummarizeResponse:
    try:
        video_id = extract_video_id(req.url)
    except TranscriptError as e:
        raise HTTPException(e.status_code, e.message)

    cache_key = f"{video_id}:{req.language}:{settings.openai_model}"
    if cached := cache.get(cache_key):
        return cached.model_copy(update={"cached": True})

    try:
        # Transcript fetch is blocking I/O; run it in a thread alongside the metadata request.
        transcript, meta = await asyncio.gather(
            asyncio.to_thread(fetch_transcript, video_id, req.language, settings.transcript_proxy_url),
            fetch_metadata(video_id),
        )
    except TranscriptError as e:
        raise HTTPException(e.status_code, e.message)

    try:
        llm_summary = await summarizer.summarize(transcript.segments, title=meta.get("title"))
    except openai.AuthenticationError:
        raise HTTPException(500, "The server's OpenAI API key is invalid.")
    except openai.RateLimitError:
        raise HTTPException(429, "OpenAI rate limit or quota reached. Try again shortly.")
    except (openai.APIError, RuntimeError) as e:
        logger.exception("Summarization failed")
        raise HTTPException(502, f"Summarization failed: {e}")

    result = build_response(transcript, meta, llm_summary, settings.openai_model)
    cache.set(cache_key, result)
    return result
