"""Generate a podcast from the command line (handy for testing auth locally)."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from .generator import LANGUAGES, LENGTHS, PodcastRequest, generate_podcast


async def _progress(text: str) -> None:
    print(f"… {text}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("topic", nargs="+", help="topic and/or URLs")
    p.add_argument("--lang", choices=sorted(LANGUAGES), default="en")
    p.add_argument("--length", choices=list(LENGTHS), default="medium")
    p.add_argument("-o", "--output", type=Path, default=Path("podcast.m4a"))
    args = p.parse_args()

    req = PodcastRequest(topic=" ".join(args.topic), language=args.lang, length=args.length)
    path = asyncio.run(generate_podcast(req, Path(".podcast-tmp"), progress=_progress))
    shutil.move(path, args.output)
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
