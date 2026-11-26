#!/usr/bin/env bash
# Raspberry Pi uploader (Mac renders, Pi uploads). Raspberry Pi OS Lite 64-bit, SSH on. On the Pi:
#   curl -fsSL https://raw.githubusercontent.com/OliverVernoum/shorts-autopilot-2/main/server/pi-setup.sh | bash
# Then from the Mac (in ~/shorts-autopilot-2):
#   ssh-copy-id pi@raspberrypi.local            # lets the Mac ship videos without a password
#   scp shorts.env pi@raspberrypi.local:~/.shorts.env
#   set "uploader": "pi" in schedule.json, push, and run: bash server/mac-setup.sh
set -euo pipefail
REPO=OliverVernoum/shorts-autopilot-2
DIR="$HOME/shorts-autopilot-2"

sudo apt-get update -q
sudo apt-get install -y -q python3-venv git rsync tzdata rclone

[ -d "$DIR" ] || git clone -q "https://github.com/$REPO.git" "$DIR"
cd "$DIR"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements-pi.txt
mkdir -p "$HOME/shorts-ready" "$HOME/.config/rclone"

# push access (it commits what it publishes): a deploy key just for this repo
mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh"
[ -f "$HOME/.ssh/shorts_deploy" ] || ssh-keygen -q -t ed25519 -N "" -f "$HOME/.ssh/shorts_deploy" -C shorts-pi
ssh-keyscan -q github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null
git config core.sshCommand "ssh -i $HOME/.ssh/shorts_deploy -o IdentitiesOnly=yes"
git remote set-url origin "git@github.com:$REPO.git"
git config user.name "Oliver Vernoum"
git config user.email "oliververnoum@outlook.com"
chmod +x server/tick.sh

( crontab -l 2>/dev/null | grep -v shorts-autopilot-2/server/tick.sh
  echo "17 * * * * $DIR/server/tick.sh upload >> $HOME/shorts-upload.log 2>&1" ) | crontab -

touch "$HOME/.shorts.env"; chmod 600 "$HOME/.shorts.env"
echo
echo "== Pi uploader installed (runs hourly at :17) =="
echo "1. Add this deploy key WITH write access at https://github.com/$REPO/settings/keys/new :"
cat "$HOME/.ssh/shorts_deploy.pub"
echo "2. From the Mac: ssh-copy-id $(whoami)@$(hostname).local && scp shorts.env $(whoami)@$(hostname).local:~/.shorts.env"
echo "3. On the Mac set \"uploader\": \"pi\" and \"pi_host\": \"$(whoami)@$(hostname).local\" in schedule.json,"
echo "   then: bash server/mac-setup.sh"
echo "Different networks? Either install Tailscale on both (pi_host = pi@<tailscale name>), or use"
echo "the Google Drive handover: on the Mac run 'rclone config' (new remote named gdrive, type drive),"
echo "then: scp ~/.config/rclone/rclone.conf $(whoami)@$(hostname).local:~/.config/rclone/rclone.conf"
echo "Log: ~/shorts-upload.log"
