#!/usr/bin/env bash
# Run by cron on the server (see setup.sh). Replaces the old GitHub Actions ticker/publish workflows.
#   tick.sh short   :07 every hour -> cyber on even UTC hours, gaming at 19, tech at 21
#   tick.sh long    :37 every hour -> long-form when UTC hour % every_hours (longform.txt) == 0
#   tick.sh test    render one cyber Short without uploading (check the setup works)
set -uo pipefail
cd "$(dirname "$0")/.."
mode=${1:-short}
exec 9>"/tmp/shorts-$mode.lock"
flock -n 9 || { echo "previous $mode run still going"; exit 0; }

set -a; . "$HOME/.shorts.env"; set +a
. .venv/bin/activate

git pull --rebase -q || { git rebase --abort 2>/dev/null; echo "git pull failed, skipping this run"; exit 1; }

h=$(date -u +%-H)
case "$mode" in
  test)
    python -m shorts.run --channel cyber --dry-run; exit $? ;;
  short)
    ch=""
    [ $((h % 2)) -eq 0 ] && ch=cyber
    [ "$h" = 19 ] && ch="${ch:+$ch,}gaming"
    [ "$h" = 21 ] && ch="${ch:+$ch,}tech"
    [ -z "$ch" ] && exit 0
    args="--channel $ch --count 1"; log=status/last-run.txt ;;
  long)
    lch=$(sed -n 's/^channels:[[:space:]]*//p' longform.txt 2>/dev/null | head -1 | tr -s ' ,' ',' | sed 's/^,//; s/,$//')
    every=$(sed -n 's/^every_hours:[[:space:]]*//p' longform.txt 2>/dev/null | head -1 | tr -dc '0-9')
    every=${every:-0}
    { [ -z "$lch" ] || [ "$lch" = none ] || [ "$every" -lt 1 ]; } && exit 0
    [ $((h % every)) -ne 0 ] && exit 0
    go=""
    for c in ${lch//,/ }; do
      ls channels/$c/longform/queue/*.json >/dev/null 2>&1 && go="$go,$c"
    done
    go=${go#,}; [ -z "$go" ] && exit 0
    args="--channel $go --longform --count 1"; log=status/last-run-long.txt ;;
  *) echo "usage: tick.sh short|long|test"; exit 2 ;;
esac

mkdir -p status out
python -m shorts.run $args 2>&1 | tee "$log"
echo "run at $(date -u +%FT%TZ) args: $args" >> "$log"

git add channels status
if ! git diff --cached --quiet; then
  git commit -qm "Publish: $(date -u +%F) $args"
  for i in 1 2 3 4 5; do
    git pull --rebase -q && git push -q && break
    sleep $((i * 7))
  done
fi
find out -type f -mtime +2 -delete 2>/dev/null   # keep the disk from filling up
