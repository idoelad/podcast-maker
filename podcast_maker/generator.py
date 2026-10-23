"""Turn a topic into a NotebookLM Audio Overview (podcast) file."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from notebooklm import NotebookLMClient
from notebooklm.types import AudioFormat, AudioLength

log = logging.getLogger(__name__)

Progress = Callable[[str], Awaitable[None]]

URL_RE = re.compile(r"https?://\S+")

# NotebookLM's lengths roughly map to: short ~5 min, default ~10 min, long ~15+ min.
LENGTHS = {
    "short": AudioLength.SHORT,
    "medium": AudioLength.DEFAULT,
    "long": AudioLength.LONG,
}

LANGUAGES = {"en": "English", "he": "Hebrew"}


@dataclass(frozen=True)
class PodcastRequest:
    topic: str
    language: str = "en"
    length: str = "medium"


@dataclass(frozen=True)
class Settings:
    max_sources: int = 8
    research_timeout: float = 15 * 60
    audio_timeout: float = 45 * 60
    keep_notebooks: bool = False


def split_topic(text: str) -> tuple[str, list[str]]:
    """Separate URLs from the free-text topic."""
    urls = [u.rstrip(").,") for u in URL_RE.findall(text)]
    topic = URL_RE.sub("", text).strip()
    return topic, urls


def build_instructions(req: PodcastRequest) -> str:
    parts = [
        "This is a personal podcast I'll listen to while cycling, so keep it "
        "conversational, concrete and easy to follow without visuals."
    ]
    if req.topic:
        parts.append(f"Focus on: {req.topic}")
    if req.language == "he":
        parts.append("The whole episode must be in Hebrew.")
    return "\n".join(parts)


async def _add_sources(client, nb_id: str, req: PodcastRequest, settings: Settings,
                       progress: Progress) -> int:
    topic, urls = split_topic(req.topic)
    if urls:
        await progress(f"Adding {len(urls)} link(s) as sources…")
        added = 0
        for url in urls[: settings.max_sources]:
            try:
                await client.sources.add_url(nb_id, url, wait=True)
                added += 1
            except Exception:
                log.exception("Failed to add %s", url)
        if added:
            return added
        if not topic:
            raise RuntimeError("None of the links could be added as sources.")

    await progress("Researching the web for sources…")
    start = await client.research.start(nb_id, topic, source="web", mode="fast")
    task = await client.research.wait_for_completion(
        nb_id, start.task_id, timeout=settings.research_timeout
    )
    sources = list(task.sources)[: settings.max_sources]
    if task.status != "completed" or not sources:
        raise RuntimeError(f"Web research found no usable sources (status: {task.status}).")
    await client.research.import_sources(nb_id, task.task_id or start.task_id, sources)
    return len(sources)


async def generate_podcast(
    req: PodcastRequest,
    out_dir: Path,
    *,
    settings: Settings = Settings(),
    progress: Progress | None = None,
    client_factory: Callable[[], object] | None = None,
) -> Path:
    """Run the full pipeline and return the path of the downloaded audio (.m4a)."""

    async def _noop(_: str) -> None:
        return None

    progress = progress or _noop
    client_factory = client_factory or (lambda: NotebookLMClient.from_storage(allow_headless=True))
    out_dir.mkdir(parents=True, exist_ok=True)

    async with client_factory() as client:
        title = split_topic(req.topic)[0] or "Podcast"
        nb = await client.notebooks.create(f"Podcast: {title[:80]}")
        try:
            count = await _add_sources(client, nb.id, req, settings, progress)
            await progress(f"Found {count} sources. Recording the episode (usually 5–15 min)…")
            status = await client.artifacts.generate_audio(
                nb.id,
                language=req.language,
                instructions=build_instructions(req),
                audio_format=AudioFormat.DEEP_DIVE,
                audio_length=LENGTHS[req.length],
            )
            final = await client.artifacts.wait_for_completion(
                nb.id, status.task_id, timeout=settings.audio_timeout, max_interval=30.0
            )
            if not final.is_complete:
                raise RuntimeError(f"Audio generation failed: {final.error or final.status}")
            path = out_dir / f"{nb.id}.m4a"
            await client.artifacts.download_audio(nb.id, str(path), status.task_id)
            return path
        finally:
            if not settings.keep_notebooks:
                try:
                    await client.notebooks.delete(nb.id)
                except Exception:
                    log.exception("Failed to delete notebook %s", nb.id)
