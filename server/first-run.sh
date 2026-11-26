#!/usr/bin/env bash
# One command on the Mac: set up, make the YouTube keys if missing, then upload the test Short.
#   bash server/first-run.sh
set -euo pipefail
cd "$(dirname "$0")/.."
git pull -q --rebase || true
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt google-auth-oauthlib
if [ ! -f shorts.env ] && [ -f "$HOME/.shorts.env" ]; then cp "$HOME/.shorts.env" shorts.env; fi
if [ ! -f shorts.env ]; then
  found=""
  for f in client_secret*.json "$HOME"/Downloads/client_secret*.json; do [ -f "$f" ] && found="$f"; done
  if [ -z "$found" ]; then
    echo
    echo "Need the Google OAuth client file first:"
    echo "  console.cloud.google.com -> your YouTube project -> APIs & Services -> Credentials"
    echo "  -> the Desktop OAuth client -> Download JSON (saves client_secret_....json to Downloads)."
    echo "Then run this again."
    open "https://console.cloud.google.com/apis/credentials" 2>/dev/null || true
    exit 1
  fi
  echo
  echo "Making shorts.env. For each channel a browser tab opens: pick that channel, click Allow."
  echo "Press s to skip Pocket Silicon (tech, paused)."
  .venv/bin/python make_env.py
fi
set -a; . ./shorts.env; set +a
echo
echo "Rendering + uploading the test Short (unlisted)..."
.venv/bin/python -m shorts.run --channel gaming --showcase tests/showcase-gaming.json
