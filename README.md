# podcast-maker

A private Telegram bot. Send it a topic (or a link), pick a language and a length, and a few minutes later you get a NotebookLM-style two-host podcast as an audio message. Telegram plays it in the background and from the lock screen, so it works on a bike ride.

```
You ──"how do bicycle gears work?"──► Telegram bot
                                         │  pick 🇬🇧/🇮🇱 · ~5 / ~10 / ~15 min
                                         ▼
                     NotebookLM (via unofficial notebooklm-py)
                     1. create a notebook
                     2. web research → import top sources   (or use your links)
                     3. generate Audio Overview (deep dive, chosen language/length)
                     4. download .m4a, delete the notebook
                                         │
You ◄──────────── audio message ─────────┘
```

> ⚠️ This project uses [notebooklm-py](https://github.com/teng-lin/notebooklm-py), an **unofficial** client for Google's private NotebookLM API. Google may change that API at any time and break it, and automating NotebookLM may go against Google's terms. Use a Google account you're OK risking, ideally a dedicated one.

## Usage

- Send any text. It's used as the topic, and the bot runs a web research step to find sources.
- Send one or more URLs (with or without extra text). Those pages become the sources, and no research step runs. Any text you add steers what the episode focuses on.
- Tap a button: 🇬🇧 or 🇮🇱, then ~5, ~10 or ~15 min. Lengths are NotebookLM's short, default and long settings, so they're approximate.
- Requests run one at a time. Generating an episode usually takes 5–15 minutes.

**Before you ride:** tap the audio once while you're on Wi-Fi so Telegram downloads it. Playback keeps going with the screen locked and shows lock-screen controls.

## Setup

### 1. Google credential (on your laptop, once)

Sign in to <https://notebooklm.google.com> with the account you'll use and check that it works. Then:

```bash
pip install "notebooklm-py[browser,headless]==0.8.5"
notebooklm login --master-token --account you@gmail.com
notebooklm auth check --test          # expect "status": "ok"
```

This writes `~/.notebooklm/profiles/default/master_token.json`. The bot uses it to create fresh session cookies on its own, so you won't need to log in again.

> The master token is a long-lived credential for the whole Google account. Changing your password does **not** revoke it. To revoke it, go to Google Account → Security → Your devices and remove the device. Treat the file like a password.

Optional: try it locally first.

```bash
pip install -e .
podcast "how do bicycle gears work" --length short -o test.m4a
podcast "מה זה טנסגריטי" --lang he
```

### 2. Telegram bot

1. In Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token it gives you.
2. Leave `TELEGRAM_ALLOWED_USER_IDS` empty for now. The first time you message the bot, it replies with your user ID. Add that ID to `.env` and restart the bot.

### 3. Hosting (free): Google Cloud e2-micro

The bot polls Telegram, so it needs no public URL, domain or HTTPS. Any always-on Linux machine with Docker works. The cheapest good option is Google Cloud's **Always Free e2-micro** VM:

1. In [console.cloud.google.com](https://console.cloud.google.com), go to Compute Engine and create a VM:
   - Machine type: **e2-micro**
   - Region: **us-west1, us-central1 or us-east1** (only these are free)
   - Boot disk: **standard persistent disk, up to 30 GB**, Debian 12

   You need a billing account to create the VM, but the free tier covers it. Each episode is about 10–20 MB of outgoing traffic, which fits easily inside the free 1 GB a month for normal personal use.
2. SSH into the VM and run:

   ```bash
   curl -fsSL https://get.docker.com | sudo sh     # Docker + compose plugin
   sudo apt-get install -y git
   sudo usermod -aG docker $USER && newgrp docker
   git clone https://github.com/idoelad/podcast-maker && cd podcast-maker
   cp .env.example .env && nano .env            # paste TELEGRAM_BOT_TOKEN
   mkdir -p notebooklm-auth/profiles/default
   ```

3. From your laptop, copy the credential to the VM:

   ```bash
   gcloud compute scp ~/.notebooklm/profiles/default/master_token.json \
       VM_NAME:~/podcast-maker/notebooklm-auth/profiles/default/
   ```

4. On the VM, fix the file permissions and start the bot:

   ```bash
   sudo chown -R 1000:1000 notebooklm-auth && chmod 600 notebooklm-auth/profiles/default/master_token.json
   docker compose up -d --build
   docker compose logs -f
   ```

Other free or cheap options: Oracle Cloud Always Free (Ampere VM), or any $4–5/month VPS such as Hetzner. Free "web app" hosts like Render or Koyeb are a poor fit, because they put idle apps to sleep and kill long-running jobs.

### Updating

```bash
git pull && docker compose up -d --build
```

If episodes start failing with auth or RPC errors, Google probably changed something. Bump `notebooklm-py` in `pyproject.toml` to the latest release and rebuild.

## Configuration (`.env`)

| Variable | Default | |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | from @BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | — | comma-separated user IDs; everyone else is refused |
| `MAX_SOURCES` | `8` | number of research results (or links) to import |
| `KEEP_NOTEBOOKS` | `false` | keep the NotebookLM notebook after each episode instead of deleting it |

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
