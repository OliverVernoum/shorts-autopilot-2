"""Batch mode (one machine renders AND uploads): render + upload ahead of time with YouTube
scheduled publishing.

  python -m shorts.run --batch [--dry-run]

Every slot (schedule.json Shorts hours + longform.txt hours) in the next `days_ahead` days that
isn't filled yet gets the next queued script, uploaded as private with publishAt = the slot.
YouTube then publishes it on time even if this machine is asleep or off.

Quota: one upload costs ~1,600 of the 10,000 daily API units per Google Cloud project, so about
6 uploads a day (`daily_upload_budget`, resets midnight Pacific). A quotaExceeded error ends the
run early; the next run carries on. Filled slots come from "scheduled_for" in published scripts.

For the Mac-renders / Pi-uploads split, see shorts/ahead.py and shorts/pi_upload.py.
"""
import datetime as dt
import json

from . import run, slots


def main(dry_run=False, tts_mode="edge"):
    cfg = slots.config()
    quota = slots.Quota(cfg, "batch.json")
    now = dt.datetime.now(slots.UTC)
    filled = slots.filled()
    empty, failed = set(), False
    for t, kind, slug in slots.slots(cfg, now):
        key = f"{kind}-{slug}"
        last = filled.get(key)
        if key in empty or (last and dt.datetime.fromisoformat(last) >= t):
            continue
        if not dry_run and quota.left() <= 0:
            run.gh_summary(f"daily upload budget ({quota.budget}) used; next run carries on")
            break
        pub = run.publish_long if kind == "long" else run.publish
        try:
            ok = pub(slug, dry_run, tts_mode, publish_at=t)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            run.gh_summary(f"::error::[{slug}] {kind} for {t:%a %H:%M}Z: {msg[:300]}")
            failed = True
            if "quota" in msg.lower():
                quota.exhaust()
                break
            empty.add(key)
            continue
        if not ok or dry_run:
            empty.add(key)
            continue
        filled[key] = t.isoformat()
        quota.spend()
    run.gh_summary(f"scheduled up to: {json.dumps(dict(sorted(filled.items())))}; "
                   f"uploads today {quota.used}/{quota.budget}")
    return 1 if failed else 0
