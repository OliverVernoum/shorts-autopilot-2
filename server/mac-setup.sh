#!/usr/bin/env bash
# Run the uploader on this Mac (instead of a server). One-time setup, from the repo folder:
#   bash server/mac-setup.sh
# Uses launchd to run `tick.sh batch` hourly at :07: videos are uploaded days ahead as scheduled
# (private + publish time), so YouTube publishes them even while the Mac is asleep or off.
# If the Mac was asleep at :07, launchd runs the job once when it wakes.
# Undo with: bash server/mac-setup.sh remove
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs"

if [ "${1:-}" = remove ]; then
  for m in short long batch render; do
    launchctl unload "$AGENTS/com.olly.shorts.$m.plist" 2>/dev/null || true
    rm -f "$AGENTS/com.olly.shorts.$m.plist"
  done
  echo "Removed. Nothing will upload from this Mac now."; exit 0
fi

BREW=$(command -v brew || ls "$HOME/.homebrew/bin/brew" /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1 || true)
[ -n "$BREW" ] || { echo "Homebrew not found. Install it from https://brew.sh then run this again."; exit 1; }
BREWBIN="$("$BREW" --prefix)/bin"
"$BREW" install -q python@3.12 ffmpeg rclone

git pull -q --rebase
git config user.name "Oliver Vernoum"
git config user.email "oliververnoum@outlook.com"

[ -d .venv ] || "$BREWBIN/python3.12" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt google-auth-oauthlib

mkdir -p "$AGENTS" "$LOGS"
# schedule.json "uploader": "mac" -> batch job (render + upload here); "pi" -> render job (ship to the Pi)
JOB=$(python3 -c 'import json;print("render" if json.load(open("schedule.json")).get("uploader")=="pi" else "batch")')
for m in short long batch render; do
  [ $m = "$JOB" ] && continue
  launchctl unload "$AGENTS/com.olly.shorts.$m.plist" 2>/dev/null || true
  rm -f "$AGENTS/com.olly.shorts.$m.plist"
done
for m in $JOB; do
  min=7
  plist="$AGENTS/com.olly.shorts.$m.plist"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.olly.shorts.$m</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$DIR/server/tick.sh</string><string>$m</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$BREWBIN:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Minute</key><integer>$min</integer></dict>
  <key>StandardOutPath</key><string>$LOGS/shorts-$m.log</string>
  <key>StandardErrorPath</key><string>$LOGS/shorts-$m.log</string>
</dict></plist>
PLIST
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist"
done

echo
echo "== Mac uploader installed =="
[ -f shorts.env ] || [ -f "$HOME/.shorts.env" ] || echo "Next: .venv/bin/python make_env.py   (makes shorts.env with your YouTube keys)"
echo "Test (renders one cyber Short, no upload):  bash server/tick.sh test"
echo "Mode: $JOB (schedule.json uploader). Logs: ~/Library/Logs/shorts-$JOB.log"
