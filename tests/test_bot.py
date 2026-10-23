from types import SimpleNamespace

from podcast_maker import bot


class Msg:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)


def update_from(user_id):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), effective_message=Msg())


async def test_first_user_claims_bot(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    assert await bot._guard(update_from(111))
    assert await bot._guard(update_from(111))
    stranger = update_from(222)
    assert not await bot._guard(stranger)
    assert "private" in stranger.effective_message.replies[0]


async def test_env_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "5, 6")
    assert await bot._guard(update_from(6))
    assert not await bot._guard(update_from(7))
    assert not (tmp_path / "owner.json").exists()


def test_has_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_HOME", str(tmp_path))
    assert not bot.has_credentials()
    (tmp_path / "profiles" / "default").mkdir(parents=True)
    (tmp_path / "profiles" / "default" / "master_token.json").write_text("{}")
    assert bot.has_credentials()
