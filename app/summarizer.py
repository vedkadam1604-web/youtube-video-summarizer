"""Turning a transcript into a structured summary with the OpenAI API."""

import asyncio

from openai import AsyncOpenAI

from .models import ChunkNotes, LLMSummary
from .transcript import Segment, to_prompt_text

SYSTEM_PROMPT = """You summarize YouTube videos from their transcripts.

The transcript is given as lines of the form "[<start second>s] <text>".
Rules:
- Only use information that is in the transcript. Never invent facts, names or numbers.
- Every timestamp you output MUST be a start second that appears in the transcript, pointing
  to where that idea is actually discussed.
- Key points should be specific and useful (numbers, names, claims, steps), not vague
  ("the speaker talks about X").
- Chapters must be in chronological order, start at or near 0, and cover the whole video.
- Write in clear, plain English regardless of the transcript's language.
- Auto-generated captions contain errors; silently fix obvious mis-transcriptions."""

MAP_PROMPT = """You are condensing one part of a long YouTube transcript into notes that will
later be merged into a full summary. Lines are "[<start second>s] <text>".
Write 8-15 dense, specific, timestamped notes covering everything important in this part.
Timestamps MUST be start seconds that appear in the text. Do not invent anything."""


def chunk_segments(segments: list[Segment], chunk_chars: int) -> list[list[Segment]]:
    chunks: list[list[Segment]] = [[]]
    size = 0
    for seg in segments:
        if size + len(seg.text) > chunk_chars and chunks[-1]:
            chunks.append([])
            size = 0
        chunks[-1].append(seg)
        size += len(seg.text) + 1
    return chunks


class Summarizer:
    def __init__(self, client: AsyncOpenAI, model: str, chunk_threshold: int, chunk_size: int):
        self.client = client
        self.model = model
        self.chunk_threshold = chunk_threshold
        self.chunk_size = chunk_size

    async def _parse(self, instructions: str, user_input: str, schema):
        response = await self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=user_input,
            text_format=schema,
        )
        if response.output_parsed is None:
            raise RuntimeError("The model did not return a valid structured response.")
        return response.output_parsed

    async def summarize(self, segments: list[Segment], title: str | None = None) -> LLMSummary:
        header = f"Video title: {title}\n\n" if title else ""
        full_text = to_prompt_text(segments)

        if len(full_text) <= self.chunk_threshold:
            return await self._parse(SYSTEM_PROMPT, f"{header}Transcript:\n{full_text}", LLMSummary)

        # Long video: map (notes per chunk, in parallel) -> reduce (final summary from notes).
        chunks = chunk_segments(segments, self.chunk_size)
        note_sets: list[ChunkNotes] = await asyncio.gather(
            *(self._parse(MAP_PROMPT, f"{header}Transcript part:\n{to_prompt_text(c)}", ChunkNotes) for c in chunks)
        )
        notes_text = "\n".join(
            f"[{n.timestamp_seconds}s] {n.point}" for notes in note_sets for n in notes.notes
        )
        return await self._parse(
            SYSTEM_PROMPT,
            f"{header}The transcript was too long, so here are timestamped notes covering "
            f"the entire video in order (treat them as the transcript):\n{notes_text}",
            LLMSummary,
        )
