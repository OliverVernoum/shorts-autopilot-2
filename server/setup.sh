#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu server (Oracle Cloud free tier). Run as the normal user:
#   curl -fsSL https://raw.githubusercontent.com/OliverVernoum/shorts-autopilot-2/main/server/setup.sh | bash
set -euo pipefail
REPO=OliverVernoum/shorts-autopilot-2
DIR="$HOME/shorts-autopilot-2"

sudo apt-get update -q
sudo apt-get install -y -q ffmpeg python3-venv git

[ -d "$DIR" ] || git clone -q "https://github.com/$REPO.git" "$DIR"
cd "$DIR"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

# push access: a deploy key just for this repo
[ -f "$HOME/.ssh/shorts_deploy" ] || ssh-keygen -q -t ed25519 -N "" -f "$HOME/.ssh/shorts_deploy" -C shorts-server
ssh-keyscan -q github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null
git config core.sshCommand "ssh -i $HOME/.ssh/shorts_deploy -o IdentitiesOnly=yes"
git remote set-url origin "git@github.com:$REPO.git"
git config user.name "Oliver Vernoum"
git config user.email "oliververnoum@outlook.com"
chmod +x server/tick.sh

# schedule (server clock is UTC; tick.sh uses UTC itself either way)
( crontab -l 2>/dev/null | grep -v shorts-autopilot-2/server/tick.sh
  echo "7 * * * * $DIR/server/tick.sh short >> $HOME/shorts-short.log 2>&1"
  echo "37 * * * * $DIR/server/tick.sh long >> $HOME/shorts-long.log 2>&1" ) | crontab -

touch "$HOME/.shorts.env"; chmod 600 "$HOME/.shorts.env"
echo
echo "== Setup done. Two things left =="
echo "1. Add this as a deploy key WITH write access at https://github.com/$REPO/settings/keys/new :"
cat "$HOME/.ssh/shorts_deploy.pub"
echo "2. Copy your shorts.env from the Mac to ~/.shorts.env on this server (see README)."
echo "Then test:  $DIR/server/tick.sh test"
