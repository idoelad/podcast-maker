#!/usr/bin/env bash
# One-command setup, run from Google Cloud Shell (works from a phone browser):
#   1. signs you in to NotebookLM (remote browser shown via Cloud Shell Web Preview)
#   2. creates a free-tier e2-micro VM
#   3. deploys the Telegram bot on it
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/idoelad/podcast-maker/HEAD/deploy/setup.sh)
#
# Re-run it any time: it skips what's already done. Pass --relogin to redo the
# Google sign-in (e.g. if the bot reports a sign-in problem).
set -euo pipefail

REPO_URL=${REPO_URL:-https://github.com/idoelad/podcast-maker.git}
VM=${VM:-podcast-bot}
ZONE=${ZONE:-us-central1-a}
STATE=$HOME/.podcast-maker
export NOTEBOOKLM_HOME=$STATE/notebooklm
PROFILE_DIR=$NOTEBOOKLM_HOME/profiles/default
RELOGIN=false
[[ ${1:-} == --relogin ]] && RELOGIN=true

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }
mkdir -p "$STATE" && chmod 700 "$STATE"

# ---------------------------------------------------------------- inputs
[[ -f $STATE/config ]] && source "$STATE/config"
[[ -n ${BOT_TOKEN:-} ]] || read -rp "Telegram bot token (from @BotFather): " BOT_TOKEN
[[ -n ${GOOGLE_EMAIL:-} ]] || read -rp "Google account email to use for NotebookLM: " GOOGLE_EMAIL
[[ $BOT_TOKEN == *:* ]] || die "That doesn't look like a Telegram bot token."
printf 'BOT_TOKEN=%q\nGOOGLE_EMAIL=%q\n' "$BOT_TOKEN" "$GOOGLE_EMAIL" > "$STATE/config"
[[ -z ${PROJECT:-} ]] || printf 'PROJECT=%q\n' "$PROJECT" >>"$STATE/config"
chmod 600 "$STATE/config"

# ---------------------------------------------------------------- project + billing
# pick NAME... : prints a numbered menu of the arguments and echoes the chosen one.
pick() {
  local i=1 choice
  for opt in "$@"; do printf '  %d) %s\n' "$i" "$opt" >&2; i=$((i + 1)); done
  while :; do
    read -rp "Choose 1-$#: " choice
    [[ $choice =~ ^[0-9]+$ ]] && ((choice >= 1 && choice <= $#)) && { echo "${!choice}"; return; }
  done
}

if [[ -z ${PROJECT:-} ]]; then
  NEW="Create a new project just for this (recommended)"
  mapfile -t PROJECTS < <(gcloud projects list --format='value(projectId)' 2>/dev/null)
  if ((${#PROJECTS[@]})); then
    say "Which Google Cloud project should the bot live in?"
    PROJECT=$(pick "$NEW" "${PROJECTS[@]}")
  else
    PROJECT=$NEW
  fi
  if [[ $PROJECT == "$NEW" ]]; then
    PROJECT=podcast-maker-$(tr -dc a-z0-9 </dev/urandom | head -c6 || true)
    say "Creating Google Cloud project $PROJECT"
    gcloud projects create "$PROJECT" --name="Podcast Maker"
  fi
  printf 'PROJECT=%q\n' "$PROJECT" >>"$STATE/config"
fi
gcloud config set project "$PROJECT" >/dev/null 2>&1
say "Using project $PROJECT"

if [[ $(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)') != True ]]; then
  mapfile -t ACCOUNTS < <(gcloud billing accounts list --filter=open=true \
    --format='value(name.basename(),displayName)' 2>/dev/null | tr '\t' ' ')
  if ((${#ACCOUNTS[@]} == 0)); then
    die "Your Google account has no billing account yet. Google requires one (with a card)
even for the free tier; you won't be charged for the free VM.

  1. Open https://console.cloud.google.com/billing/create and create one.
  2. Come back here and run the same command again. It picks up where it left off."
  elif ((${#ACCOUNTS[@]} == 1)); then
    ACCOUNT=${ACCOUNTS[0]}
  else
    say "Which billing account should pay for (free-tier) usage?"
    ACCOUNT=$(pick "${ACCOUNTS[@]}")
  fi
  say "Linking billing account ${ACCOUNT#* } to $PROJECT"
  gcloud billing projects link "$PROJECT" --billing-account="${ACCOUNT%% *}" >/dev/null
fi
say "Enabling the Compute Engine API (takes a minute the first time)"
gcloud services enable compute.googleapis.com

# ---------------------------------------------------------------- Google sign-in
if $RELOGIN || [[ ! -f $PROFILE_DIR/master_token.json ]]; then
  say "Installing sign-in tools (a couple of minutes)"
  sudo apt-get update -qq >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb x11vnc novnc websockify >/dev/null
  [[ -x $STATE/venv/bin/notebooklm ]] || python3 -m venv "$STATE/venv"
  "$STATE/venv/bin/pip" install -q --upgrade "notebooklm-py[browser,headless]==0.8.5"
  "$STATE/venv/bin/python" -m playwright install chromium >/dev/null
  sudo "$STATE/venv/bin/python" -m playwright install-deps chromium >/dev/null 2>&1 || true
  CHROME=$("$STATE/venv/bin/python" -c \
    'from playwright.sync_api import sync_playwright as s; p=s().start(); print(p.chromium.executable_path); p.stop()')

  PIDS=()
  cleanup() { kill "${PIDS[@]}" 2>/dev/null || true; rm -rf /tmp/podcast-login-chrome; }
  trap cleanup EXIT
  Xvfb :99 -screen 0 500x900x24 -nolisten tcp & PIDS+=($!)
  sleep 1
  DISPLAY=:99 "$CHROME" --remote-debugging-port=9222 --user-data-dir=/tmp/podcast-login-chrome \
    --window-size=500,900 --window-position=0,0 --kiosk --no-first-run --no-default-browser-check \
    --disable-dev-shm-usage about:blank >/dev/null 2>&1 & PIDS+=($!)
  # Bound to localhost; reachable only through your authenticated Cloud Shell Web Preview.
  x11vnc -display :99 -rfbport 5900 -localhost -nopw -forever -shared -quiet >/dev/null 2>&1 & PIDS+=($!)
  websockify --web /usr/share/novnc 8080 localhost:5900 >/dev/null 2>&1 & PIDS+=($!)
  sleep 3

  PREVIEW=$(cloudshell get-web-preview-url -p 8080 2>/dev/null || true)
  say "Sign in to Google"
  if [[ -n $PREVIEW ]]; then
    echo "Open this link (same browser), then sign in as $GOOGLE_EMAIL:"
    echo
    echo "    ${PREVIEW%/}/vnc.html?autoconnect=1&resize=scale"
  else
    echo "Tap the Web Preview button (top right) -> 'Preview on port 8080',"
    echo "add /vnc.html to the end of the address, and sign in as $GOOGLE_EMAIL."
  fi
  echo
  echo "Tip: to type on a phone, open the small tab on the left edge and tap the keyboard icon."
  echo "Waiting up to 15 minutes. This terminal continues automatically once you're signed in."
  DISPLAY=:99 "$STATE/venv/bin/notebooklm" login --master-token --force --account "$GOOGLE_EMAIL" \
    --cdp-url http://127.0.0.1:9222 --browser-timeout 900 \
    || die "Sign-in didn't complete. Re-run this command to try again."
  cleanup
  trap - EXIT
fi

# ---------------------------------------------------------------- VM
STARTUP=$(mktemp)
cat >"$STARTUP" <<'EOF'
#!/bin/bash
# Runs as root on every boot: install Docker, fetch the latest code, (re)start the bot.
set -e
exec >>/var/log/podcast-maker.log 2>&1
MD=http://metadata.google.internal/computeMetadata/v1/instance/attributes
REPO=$(curl -fs -H Metadata-Flavor:Google $MD/repo-url)
if [ ! -f /swapfile ]; then fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile; fi
swapon /swapfile 2>/dev/null || true
command -v git >/dev/null || { apt-get update && apt-get install -y git; }
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
if [ -d /opt/podcast-maker/.git ]; then git -C /opt/podcast-maker pull --ff-only || true
else git clone "$REPO" /opt/podcast-maker; fi
cd /opt/podcast-maker
mkdir -p data/notebooklm/profiles/default && chown -R 1000:1000 data
touch .provisioned
if [ -f .env ]; then docker compose up -d --build; fi
EOF

if ! gcloud compute instances describe "$VM" --zone "$ZONE" >/dev/null 2>&1; then
  say "Creating free-tier VM $VM in $ZONE"
  gcloud compute instances create "$VM" --zone "$ZONE" --machine-type e2-micro \
    --image-family debian-12 --image-project debian-cloud \
    --boot-disk-size 30GB --boot-disk-type pd-standard \
    --metadata-from-file startup-script="$STARTUP" --metadata repo-url="$REPO_URL"
else
  gcloud compute instances add-metadata "$VM" --zone "$ZONE" \
    --metadata-from-file startup-script="$STARTUP" --metadata repo-url="$REPO_URL"
fi

SSH=(gcloud compute ssh "$VM" --zone "$ZONE" --quiet --strict-host-key-checking=no)
say "Waiting for the VM to install Docker and the code (3-5 minutes)"
until "${SSH[@]}" --command 'test -f /opt/podcast-maker/.provisioned' -- -o ConnectTimeout=10 >/dev/null 2>&1; do
  sleep 15
done

say "Deploying the bot"
ENVFILE=$(mktemp)
printf 'TELEGRAM_BOT_TOKEN=%s\n' "$BOT_TOKEN" >"$ENVFILE"
"${SSH[@]}" --command 'rm -rf /tmp/podcast-upload && mkdir -m 700 /tmp/podcast-upload' >/dev/null
gcloud compute scp --zone "$ZONE" --quiet --strict-host-key-checking=no \
  "$PROFILE_DIR"/*.json "$ENVFILE" "$VM":/tmp/podcast-upload/ >/dev/null
rm -f "$ENVFILE" "$STARTUP"
"${SSH[@]}" --command "sudo bash -s $(basename "$ENVFILE")" <<'EOF'
set -e
U=/tmp/podcast-upload
cd /opt/podcast-maker
git pull --ff-only -q || true
P=data/notebooklm/profiles/default
for f in "$U"/*.json; do install -o 1000 -g 1000 -m 600 "$f" "$P/$(basename "$f")"; done
[ -f .env ] || cp .env.example .env
TOKEN=$(sed -n 's/^TELEGRAM_BOT_TOKEN=//p' "$U/$1")
sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=$TOKEN|" .env
chmod 600 .env
rm -rf "$U"
docker compose up -d --build --force-recreate
EOF

say "All done! 🎉"
echo "Open Telegram, find your bot, send /start, then send it a topic."
echo "(The first person to message the bot becomes its only allowed user.)"
