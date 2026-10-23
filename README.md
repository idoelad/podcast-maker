# podcast-maker

A private Telegram bot. Send it a topic (or a link), pick a language and a length, and a few minutes later you get a NotebookLM two-host podcast as an audio message. Telegram plays it in the background and from the lock screen, so it works on a bike ride.

```
You ──"how do bicycle gears work?"──► Telegram bot (free Google Cloud VM)
                                         │  pick 🇬🇧/🇮🇱 · ~5 / ~10 / ~15 min
                                         ▼
                     NotebookLM (via unofficial notebooklm-py)
                     1. create a notebook
                     2. web research → import top sources   (or use your links)
                     3. generate the Audio Overview
                     4. download it, delete the notebook
                                         │
You ◄──────────── audio message ─────────┘
```

> ⚠️ This project uses [notebooklm-py](https://github.com/teng-lin/notebooklm-py), an **unofficial** client for Google's private NotebookLM API. Google may change that API at any time and break it, and automating NotebookLM may go against Google's terms. Use a Google account you're OK risking.

## Setup (all from your phone, about 15 minutes)

1. **Make this repo public.** In GitHub, go to Settings → General → Danger Zone → Change visibility → Public. The free server downloads the code from GitHub. The repo contains no secrets.
2. **Create the Telegram bot.** Open [@BotFather](https://t.me/BotFather), send `/newbot`, pick a name, and copy the token it gives you.
3. **Run the setup script in Google Cloud Shell.** Open <https://shell.cloud.google.com> in your phone's browser and sign in with your Google account. If you've never used Google Cloud, first accept the terms and add a billing card at <https://console.cloud.google.com/billing>; the free tier still requires one. Then paste:

   ```bash
   bash <(curl -fsSL https://raw.githubusercontent.com/idoelad/podcast-maker/HEAD/deploy/setup.sh)
   ```

   The script asks for the bot token and your Google email. It then prints a **link**. Open that link in the same browser: it shows a remote browser window on Google's sign-in page. Sign in there. The script then finishes by itself: it creates a free e2-micro VM and starts the bot on it.
4. **Send `/start` to your bot in Telegram.** The first person to message the bot becomes its only allowed user, so do this right away.

**If Google sign-in ever breaks** (the bot will say so), open Cloud Shell and run the same command with `--relogin` at the end.

**Updating:** the VM pulls the latest code every time it reboots. To update immediately, re-run the setup command; it skips the steps that are already done.

## Using it

- Send any text. It's used as the topic, and the bot runs a web research step to find sources.
- Send one or more URLs (with or without extra text). Those pages become the sources. Any text you add steers what the episode focuses on.
- Tap a button: 🇬🇧 or 🇮🇱, then ~5, ~10 or ~15 min. Lengths are NotebookLM's short, default and long settings, so they're approximate.
- An episode usually takes 5–15 minutes. Requests run one at a time.
- **Before you ride:** tap the audio once while you're on Wi-Fi so Telegram downloads it. Playback keeps going with the screen locked.

## Costs and security

- **Cost:** the e2-micro VM and its 30 GB standard disk are in Google Cloud's Always Free tier (in us-central1). Google may charge a few dollars a month for the VM's external IPv4 address, so check the Billing page after the first week. Each episode uses about 15 MB of outgoing traffic, well inside the free 1 GB a month.
- **Google credential:** the bot stores a long-lived NotebookLM "master token" on the VM so it can sign itself back in. Anyone holding that file has broad access to the Google account, and changing your password does **not** revoke it. To revoke it, go to Google Account → Security → Your devices and remove the device. A separate Google account is the safest choice.
- **Sign-in page:** the remote browser used for sign-in runs only inside your Cloud Shell. It's reachable only through Cloud Shell's Web Preview, which requires your Google login, and it shuts down when the script continues.

## Configuration

These settings are in `/opt/podcast-maker/.env` on the VM:

| Variable | Default | |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | set by the setup script |
| `TELEGRAM_ALLOWED_USER_IDS` | — | optional comma-separated allowlist (otherwise the first user claims the bot) |
| `MAX_SOURCES` | `8` | number of research results (or links) to import |
| `KEEP_NOTEBOOKS` | `false` | keep each NotebookLM notebook instead of deleting it |

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
podcast "how do bicycle gears work" --length short   # local run; needs `notebooklm login` first
```

Run it anywhere else with Docker: put the credential files in `data/notebooklm/profiles/default/`, copy `.env.example` to `.env`, then run `docker compose up -d --build`.
