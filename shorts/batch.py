"""Batch mode: render + upload ahead of time with YouTube scheduled publishing.

  python -m shorts.run --batch [--dry-run]

Every slot (schedule.json Shorts hours + longform.txt hours) in the next `days_ahead` days that
isn't filled yet gets the next queued script, uploaded as private with publishAt = the slot.
YouTube then publishes it on time even if this machine is asleep or off.

Quota: one upload costs ~1,600 of the 10,000 daily API units per Google Cloud project, so about
6 uploads a day. `daily_upload_budget` caps uploads per quota day (resets midnight Pacific), and
a quotaExceeded error ends the run early; the next run carries on. Earliest slots fill first.
Filled slots are read from the "scheduled_for" field of published scripts (in git), so this works
from any machine; .state/batch.json only counts uploads used today.
"""
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

from . import run

ROOT = run.ROOT
STATE = os.path.join(ROOT, ".state", "batch.json")
UTC = dt.timezone.utc


def _load(path, default):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def _longform_hours():
    hours = {}
    p = os.path.join(ROOT, "longform.txt")
    for line in open(p) if os.path.exists(p) else []:
        line = line.split("#")[0].strip()
        if ":" in line:
            c, h = (x.strip() for x in line.split(":", 1))
            if c and h.isdigit():
                hours[c] = [int(h)]
    return hours


def _filled():
    """Latest scheduled_for per 'short-<slug>' / 'long-<slug>' from published scripts in git."""
    filled = {}
    for slug in os.listdir(run.CH_ROOT):
        for kind, sub in (("short", "published"), ("long", os.path.join("longform", "published"))):
            d = os.path.join(run.CH_ROOT, slug, sub)
            for f in os.listdir(d) if os.path.isdir(d) else []:
                js = _load(os.path.join(d, f), {}) if f.endswith(".json") else {}
                at = js.get("scheduled_for") or js.get("published_at")  # older direct uploads
                if at and at > filled.get(f"{kind}-{slug}", ""):
                    filled[f"{kind}-{slug}"] = at
    return filled


def _slots(cfg, now):
    """[(time, kind, slug)] for every slot from now+1h up to days_ahead, earliest first."""
    out, minute = [], cfg.get("minute", 7)
    plans = [("short", s, hs) for s, hs in cfg.get("shorts", {}).items()] + \
            [("long", s, hs) for s, hs in _longform_hours().items()]
    soon = now + dt.timedelta(hours=1)  # YouTube needs publishAt in the future; leave processing time
    for d in range(cfg.get("days_ahead", 3) + 1):
        day = (now + dt.timedelta(days=d)).date()
        for kind, slug, hours in plans:
            for h in hours:
                t = dt.datetime(day.year, day.month, day.day, h, minute, tzinfo=UTC)
                if soon <= t <= now + dt.timedelta(days=cfg.get("days_ahead", 3)):
                    out.append((t, kind, slug))
    rank = {s: i for i, s in enumerate(cfg.get("priority", []))}
    # fill day by day; within a day the priority channel gets the quota first
    return sorted(out, key=lambda x: (x[0].date(), rank.get(x[2], 99), x[0]))


def main(dry_run=False, tts_mode="edge"):
    cfg = _load(os.path.join(ROOT, "schedule.json"), {})
    state = _load(STATE, {"quota": {}})
    filled = _filled()
    now = dt.datetime.now(UTC)
    qday = now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    if state["quota"].get("day") != qday:
        state["quota"] = {"day": qday, "used": 0}
    budget = cfg.get("daily_upload_budget", 6)
    empty = set()
    failed = False

    def save():
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(state, open(STATE, "w"), indent=2)

    for t, kind, slug in _slots(cfg, now):
        key = f"{kind}-{slug}"
        last = filled.get(key)
        if key in empty or (last and dt.datetime.fromisoformat(last) >= t):
            continue
        if not dry_run and state["quota"]["used"] >= budget:
            run.gh_summary(f"daily upload budget ({budget}) used; next run carries on")
            break
        pub = run.publish_long if kind == "long" else run.publish
        try:
            ok = pub(slug, dry_run, tts_mode, publish_at=t)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            run.gh_summary(f"::error::[{slug}] {kind} for {t:%a %H:%M}Z: {msg[:300]}")
            failed = True
            if "quota" in msg.lower():
                state["quota"]["used"] = budget  # stop until the quota resets
                break
            empty.add(key)  # don't hammer a broken channel this run
            continue
        if not ok:
            empty.add(key)  # queue empty or no token
            continue
        if dry_run:
            run.gh_summary(f"[{slug}] dry run: would schedule {kind} for {t.isoformat()}")
            empty.add(key)
            continue
        filled[key] = t.isoformat()
        state["quota"]["used"] += 1
        save()
    save()
    ahead = dict(sorted(filled.items()))
    run.gh_summary(f"scheduled up to: {json.dumps(ahead)}; uploads today {state['quota']['used']}/{budget}")
    return 1 if failed else 0
