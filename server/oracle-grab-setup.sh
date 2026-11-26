#!/usr/bin/env bash
# Install the Oracle CLI and start oracle-grab.sh every 5 minutes (until it gets the server).
#   bash server/oracle-grab-setup.sh          start
#   bash server/oracle-grab-setup.sh remove   stop
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.olly.oracle-grab.plist"
if [ "${1:-}" = remove ]; then launchctl unload "$PLIST" 2>/dev/null || true; rm -f "$PLIST"; echo "Stopped."; exit 0; fi

BREW=$(command -v brew || ls "$HOME/.homebrew/bin/brew" /opt/homebrew/bin/brew /usr/local/bin/brew 2>/dev/null | head -1 || true)
[ -n "$BREW" ] || { echo "Homebrew not found (https://brew.sh)"; exit 1; }
BREWBIN="$("$BREW" --prefix)/bin"
command -v oci >/dev/null || [ -x "$BREWBIN/oci" ] || "$BREW" install -q oci-cli
[ -f .oci/config ] || { echo "Missing .oci/config - ask Claude to set up the Oracle API key"; exit 1; }
chmod +x server/oracle-grab.sh
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.olly.oracle-grab</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/server/oracle-grab.sh</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$BREWBIN:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/oracle-grab.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/oracle-grab.log</string>
</dict></plist>
PLIST
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Started. It tries every 5 minutes and pops up a notification when the server is ready."
echo "Watch it: tail -f ~/Library/Logs/oracle-grab.log"
