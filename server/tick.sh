#!/usr/bin/env bash
# Run every hour by cron (server) or launchd (Mac). Replaces the old GitHub Actions workflows.
#   tick.sh short   :07 -> 2 Shorts a day per channel (slots below)
#   tick.sh long    :37 -> 1 long-form a day per channel (hours in longform.txt)
#   tick.sh batch   upload ahead with YouTube scheduled publishing (schedule.json); Mac default
#   tick.sh test    render one cyber Short without uploading
# Each slot counts as due once its UTC hour has passed, so if the machine was asleep the
# missed upload happens at the next tick that day (one per channel per tick).
set -uo pipefail
cd "$(dirname "$0")/.."
mode=${1:-short}

# Shorts slots (UTC hours) per channel
SHORT_SLOTS_cyber="8 17"
SHORT_SLOTS_gaming="10 19"
SHORT_SLOTS_tech="12 21"

lock="/tmp/shorts-$mode.lock"
if ! mkdir "$lock" 2>/dev/null; then
  if [ -n "$(find "$lock" -maxdepth 0 -mmin +360 2>/dev/null)" ]; then rm -rf "$lock"; mkdir "$lock"
  else echo "previous $mode run still going"; exit 0; fi
fi
trap 'rm -rf "$lock"' EXIT

for f in "$HOME/.shorts.env" shorts.env; do
  [ -f "$f" ] && { set -a; . "$f"; set +a; break; }
done
. .venv/bin/activate

if [ "$mode" = test ]; then python -m shorts.run --channel cyber --dry-run; exit $?; fi

git pull --rebase --autostash -q || { git rebase --abort 2>/dev/null; echo "git pull failed, skipping this run"; exit 1; }

h=$((10#$(date -u +%H)))
today=$(date -u +%F)
mkdir -p .state status out
done_today() { f=".state/$1"; [ "$(sed -n 1p "$f" 2>/dev/null)" = "$today" ] && sed -n 2p "$f" || echo 0; }
mark_done()  { n=$(( $(done_today "$1") + 1 )); printf '%s\n%s\n' "$today" "$n" > ".state/$1"; }
due_count()  { n=0; for s in $1; do [ "$h" -ge "$s" ] && n=$((n+1)); done; echo $n; }

case "$mode" in
  short)
    log=status/last-run.txt; : > "$log"
    for c in cyber gaming tech; do
      slots_var="SHORT_SLOTS_$c"; slots=${!slots_var}
      [ "$(done_today short-$c)" -ge "$(due_count "$slots")" ] && continue
      tok="YT_REFRESH_TOKEN_$(echo "$c" | tr a-z A-Z)"
      [ -n "${!tok:-}" ] || { echo "[$c] no $tok in shorts.env yet, skipping" >> "$log"; continue; }
      python -m shorts.run --channel "$c" --count 1 2>&1 | tee -a "$log" && mark_done "short-$c"
    done ;;
  long)
    log=status/last-run-long.txt; : > "$log"
    while IFS=: read -r c hr; do
      c=$(echo "$c" | tr -d ' '); hr=$(echo "$hr" | tr -dc '0-9')
      case "$c" in ''|\#*) continue ;; esac
      [ -z "$hr" ] && continue
      [ "$(done_today long-$c)" -ge "$(due_count "$hr")" ] && continue
      ls channels/$c/longform/queue/*.json >/dev/null 2>&1 || continue
      tok="YT_REFRESH_TOKEN_$(echo "$c" | tr a-z A-Z)"
      [ -n "${!tok:-}" ] || continue
      python -m shorts.run --channel "$c" --longform --count 1 2>&1 | tee -a "$log" && mark_done "long-$c"
    done < longform.txt ;;
  batch)
    log=status/last-run-batch.txt; : > "$log"
    python -m shorts.run --batch 2>&1 | tee -a "$log" ;;
  *) echo "usage: tick.sh short|long|batch|test"; exit 2 ;;
esac

[ -s "$log" ] || exit 0
echo "run at $(date -u +%FT%TZ) ($mode)" >> "$log"
git add channels status
if ! git diff --cached --quiet; then
  git commit -qm "Publish: $(date -u +%F) $mode"
  for i in 1 2 3 4 5; do
    git pull --rebase --autostash -q && git push -q && break
    sleep $((i * 7))
  done
fi
find out -type f -mtime +2 -delete 2>/dev/null
