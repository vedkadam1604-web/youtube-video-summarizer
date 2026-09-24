from pydantic import BaseModel, Field

# ---------- Schemas the LLM must fill (OpenAI structured outputs) ----------


class KeyPoint(BaseModel):
    point: str = Field(description="One concrete, self-contained insight from the video.")
    timestamp_seconds: int = Field(description="Second in the video where this point is made.")


class Chapter(BaseModel):
    title: str = Field(description="Short chapter title (max ~8 words).")
    start_seconds: int = Field(description="Second where this chapter starts.")
    summary: str = Field(description="1-3 sentence summary of the chapter.")


class LLMSummary(BaseModel):
    tldr: str = Field(description="One or two sentence summary of the whole video.")
    summary: str = Field(description="A single well-written paragraph (4-7 sentences) summarizing the video.")
    key_points: list[KeyPoint] = Field(description="5-10 most important points, in chronological order.")
    chapters: list[Chapter] = Field(description="3-10 chapters covering the full video, in order.")
    topics: list[str] = Field(description="3-6 short topic tags.")


class ChunkNotes(BaseModel):
    """Intermediate output of the map step for long videos."""

    notes: list[KeyPoint] = Field(description="Dense, timestamped notes covering this part of the video.")


# ---------- API request / response ----------


class SummarizeRequest(BaseModel):
    url: str = Field(examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
    language: str = Field(default="en", description="Preferred transcript language (ISO code).")


class TimestampedKeyPoint(KeyPoint):
    timestamp: str
    link: str


class TimestampedChapter(Chapter):
    timestamp: str
    link: str


class VideoMeta(BaseModel):
    video_id: str
    url: str
    title: str | None = None
    channel: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int
    transcript_language: str
    transcript_is_generated: bool


class SummarizeResponse(BaseModel):
    video: VideoMeta
    tldr: str
    summary: str
    key_points: list[TimestampedKeyPoint]
    chapters: list[TimestampedChapter]
    topics: list[str]
    model: str
    cached: bool = False
