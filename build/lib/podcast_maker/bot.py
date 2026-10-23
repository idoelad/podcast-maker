"""Telegram bot: send a topic, get a podcast back."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .generator import LANGUAGES, LENGTHS, PodcastRequest, Settings, generate_podcast, split_topic

log = logging.getLogger(__name__)

HELP = (
    "Send me a topic (or a link, or both) and pick a language and length.\n"
    "I'll research it with NotebookLM and send back a podcast episode.\n\n"
    "Examples:\n"
    "• How do bicycle gears work?\n"
    "• The history of the Tour de France\n"
    "• https://en.wikipedia.org/wiki/Tensegrity explain the core idea"
)

KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton(f"🇬🇧 {label}", callback_data=f"en:{length}")
         for length, label in (("short", "~5 min"), ("medium", "~10 min"), ("long", "~15 min"))],
        [InlineKeyboardButton(f"🇮🇱 {label}", callback_data=f"he:{length}")
         for length, label in (("short", "~5 min"), ("medium", "~10 min"), ("long", "~15 min"))],
    ]
)


def parse_choice(data: str) -> tuple[str, str]:
    language, length = data.split(":", 1)
    if language not in LANGUAGES or length not in LENGTHS:
        raise ValueError(data)
    return language, length


def allowed_ids() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


async def _guard(update: Update) -> bool:
    user = update.effective_user
    if user and user.id in allowed_ids():
        return True
    if update.effective_message:
        await update.effective_message.reply_text(
            f"Sorry, this is a private bot. (Your user ID is {user.id if user else '?'} — "
            "add it to TELEGRAM_ALLOWED_USER_IDS if this is your bot.)"
        )
    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _guard(update):
        await update.message.reply_text(HELP)


async def on_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    context.user_data["topic"] = update.message.text.strip()
    await update.message.reply_text("Which language and length?", reply_markup=KEYBOARD)


async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _guard(update):
        return
    topic = context.user_data.pop("topic", None)
    if not topic:
        await query.edit_message_text("Send me a topic first.")
        return
    language, length = parse_choice(query.data)
    req = PodcastRequest(topic=topic, language=language, length=length)
    context.application.create_task(_run_job(query.message, req, context), update=update)


async def _run_job(status_msg, req: PodcastRequest, context: ContextTypes.DEFAULT_TYPE) -> None:
    lock: asyncio.Lock = context.application.bot_data.setdefault("lock", asyncio.Lock())
    label = f"“{req.topic[:200]}” · {LANGUAGES[req.language]} · {req.length}"

    async def progress(text: str) -> None:
        try:
            await status_msg.edit_text(f"{label}\n\n⏳ {text}")
        except Exception:  # e.g. "message is not modified"
            log.debug("progress edit failed", exc_info=True)

    if lock.locked():
        await progress("Queued behind another episode…")
    async with lock:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                path = await generate_podcast(
                    req, Path(tmp), settings=context.application.bot_data["settings"],
                    progress=progress,
                )
                await progress("Uploading…")
                title = split_topic(req.topic)[0] or "Podcast"
                with path.open("rb") as f:
                    await status_msg.reply_audio(
                        f, title=title[:64], performer="Podcast Maker",
                        filename=f"{title[:40]}.m4a", read_timeout=300, write_timeout=300,
                    )
                await status_msg.edit_text(f"{label}\n\n✅ Done — enjoy the ride!")
            except Exception as e:
                log.exception("Job failed")
                await status_msg.edit_text(f"{label}\n\n❌ Failed: {e}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).concurrent_updates(True).build()
    app.bot_data["settings"] = Settings(
        max_sources=int(os.environ.get("MAX_SOURCES", "8")),
        keep_notebooks=os.environ.get("KEEP_NOTEBOOKS", "").lower() in ("1", "true", "yes"),
    )
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_topic))
    app.add_handler(CallbackQueryHandler(on_choice))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
