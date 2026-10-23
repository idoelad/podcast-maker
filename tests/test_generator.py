from pathlib import Path
from types import SimpleNamespace

import pytest

from podcast_maker.bot import parse_choice
from podcast_maker.generator import (
    AudioLength,
    PodcastRequest,
    build_instructions,
    generate_podcast,
    split_topic,
)


class FakeClient:
    def __init__(self, research_sources=("a", "b"), audio_ok=True):
        self.calls = []
        self.research_sources = research_sources
        self.audio_ok = audio_ok
        outer = self

        class Notebooks:
            async def create(self, title):
                outer.calls.append(("create", title))
                return SimpleNamespace(id="nb1")

            async def delete(self, nb_id):
                outer.calls.append(("delete", nb_id))

        class Sources:
            async def add_url(self, nb_id, url, wait=False):
                outer.calls.append(("add_url", url))

        class Research:
            async def start(self, nb_id, query, source, mode):
                outer.calls.append(("research", query))
                return SimpleNamespace(task_id="r1")

            async def wait_for_completion(self, nb_id, task_id, timeout):
                srcs = tuple(SimpleNamespace(url=s, title=s) for s in outer.research_sources)
                return SimpleNamespace(status="completed", sources=srcs, task_id=task_id)

            async def import_sources(self, nb_id, task_id, sources):
                outer.calls.append(("import", len(sources)))

        class Artifacts:
            async def generate_audio(self, nb_id, **kw):
                outer.calls.append(("audio", kw))
                return SimpleNamespace(task_id="a1")

            async def wait_for_completion(self, nb_id, task_id, **kw):
                return SimpleNamespace(is_complete=outer.audio_ok, error="boom", status="failed")

            async def download_audio(self, nb_id, path, artifact_id):
                Path(path).write_bytes(b"audio")

        self.notebooks, self.sources = Notebooks(), Sources()
        self.research, self.artifacts = Research(), Artifacts()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_split_topic():
    assert split_topic("explain https://x.com/a, please") == ("explain  please", ["https://x.com/a"])
    assert split_topic("just a topic") == ("just a topic", [])


def test_instructions_hebrew():
    assert "Hebrew" in build_instructions(PodcastRequest("x", language="he"))
    assert "Hebrew" not in build_instructions(PodcastRequest("x"))


def test_parse_choice():
    assert parse_choice("he:long") == ("he", "long")
    with pytest.raises(ValueError):
        parse_choice("fr:long")


async def test_topic_uses_research(tmp_path):
    fake = FakeClient()
    path = await generate_podcast(
        PodcastRequest("bike gears", "he", "long"), tmp_path, client_factory=lambda: fake
    )
    assert path.read_bytes() == b"audio"
    names = [c[0] for c in fake.calls]
    assert names == ["create", "research", "import", "audio", "delete"]
    audio_kw = fake.calls[3][1]
    assert audio_kw["language"] == "he" and audio_kw["audio_length"] == AudioLength.LONG


async def test_urls_skip_research(tmp_path):
    fake = FakeClient()
    await generate_podcast(
        PodcastRequest("https://example.com/post"), tmp_path, client_factory=lambda: fake
    )
    assert "research" not in [c[0] for c in fake.calls]
    assert ("add_url", "https://example.com/post") in fake.calls


async def test_failure_still_deletes_notebook(tmp_path):
    fake = FakeClient(audio_ok=False)
    with pytest.raises(RuntimeError, match="boom"):
        await generate_podcast(PodcastRequest("x"), tmp_path, client_factory=lambda: fake)
    assert fake.calls[-1] == ("delete", "nb1")


async def test_no_sources_found(tmp_path):
    fake = FakeClient(research_sources=())
    with pytest.raises(RuntimeError, match="no usable sources"):
        await generate_podcast(PodcastRequest("x"), tmp_path, client_factory=lambda: fake)
