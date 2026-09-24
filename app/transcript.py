"""Fetching YouTube transcripts and metadata."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx
import requests
from youtube_transcript_api import (
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)
from youtube_transcript_api.proxies import GenericProxyConfig

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class TranscriptError(Exception):
    """User-facing error with an HTTP status code."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Segment:
    start: float
    text: str


@dataclass
class Transcript:
    video_id: str
    segments: list[Segment]
    language: str
    is_generated: bool

    @property
    def duration_seconds(self) -> int:
        return int(self.segments[-1].start) if self.segments else 0


def extract_video_id(url: str) -> str:
    """Accepts watch, youtu.be, shorts, embed, live and music URLs, or a bare video ID."""
    url = url.strip()
    if VIDEO_ID_RE.match(url):
        return url
    if not re.match(r"^https?://", url):
        url = "https://" + url

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    path_parts = [p for p in parsed.path.split("/") if p]

    candidate = None
    if host == "youtu.be" and path_parts:
        candidate = path_parts[0]
    elif host in {"youtube.com", "music.youtube.com", "youtube-nocookie.com"}:
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live", "v"}:
            candidate = path_parts[1]

    if candidate and VIDEO_ID_RE.match(candidate):
        return candidate
    raise TranscriptError("That doesn't look like a valid YouTube video URL.", 422)


def format_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _client(proxy_url: str | None) -> YouTubeTranscriptApi:
    if proxy_url:
        return YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=proxy_url, https_url=proxy_url))
    return YouTubeTranscriptApi()


def fetch_transcript(video_id: str, language: str = "en", proxy_url: str | None = None) -> Transcript:
    """Prefer a manual transcript in the requested language, then a generated one,
    then anything available (translated to the requested language when possible)."""
    api = _client(proxy_url)
    try:
        transcripts = api.list(video_id)
        langs = [language] if language == "en" else [language, "en"]
        try:
            chosen = transcripts.find_transcript(langs)
        except NoTranscriptFound:
            chosen = next(iter(transcripts))
            if chosen.is_translatable and any(t.language_code == language for t in chosen.translation_languages):
                chosen = chosen.translate(language)
        fetched = chosen.fetch()
    except TranscriptsDisabled:
        raise TranscriptError("Captions are disabled for this video, so it can't be summarized.", 404)
    except (NoTranscriptFound, StopIteration):
        raise TranscriptError("No transcript is available for this video.", 404)
    except VideoUnavailable:
        raise TranscriptError("This video is unavailable (private, deleted, or region-locked).", 404)
    except AgeRestricted:
        raise TranscriptError("This video is age-restricted, so its transcript can't be fetched.", 403)
    except (IpBlocked, RequestBlocked):
        raise TranscriptError(
            "YouTube is blocking transcript requests from this server. "
            "Set TRANSCRIPT_PROXY_URL to route requests through a proxy.",
            503,
        )
    except (YouTubeTranscriptApiException, requests.RequestException) as e:
        raise TranscriptError(f"Couldn't fetch the transcript from YouTube ({type(e).__name__}).", 502)

    segments = [Segment(start=s.start, text=s.text.replace("\n", " ").strip()) for s in fetched.snippets]
    segments = [s for s in segments if s.text]
    if not segments:
        raise TranscriptError("The transcript for this video is empty.", 404)
    return Transcript(
        video_id=video_id,
        segments=segments,
        language=fetched.language_code,
        is_generated=fetched.is_generated,
    )


def to_prompt_text(segments: list[Segment], block_seconds: int = 20) -> str:
    """Merge tiny caption snippets into ~20s blocks, each prefixed with its start second.
    Fewer, larger blocks = fewer tokens, while keeping timestamps precise enough."""
    lines: list[str] = []
    block_start, block_text = None, []
    for seg in segments:
        if block_start is None:
            block_start = seg.start
        block_text.append(seg.text)
        if seg.start - block_start >= block_seconds:
            lines.append(f"[{int(block_start)}s] {' '.join(block_text)}")
            block_start, block_text = None, []
    if block_text:
        lines.append(f"[{int(block_start)}s] {' '.join(block_text)}")
    return "\n".join(lines)


async def fetch_metadata(video_id: str) -> dict:
    """Title/channel/thumbnail via YouTube's public oEmbed endpoint (no API key needed)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"})
            r.raise_for_status()
            data = r.json()
            return {
                "title": data.get("title"),
                "channel": data.get("author_name"),
                "thumbnail_url": data.get("thumbnail_url"),
            }
    except (httpx.HTTPError, ValueError):
        return {"title": None, "channel": None, "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}
