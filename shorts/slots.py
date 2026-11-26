"""Upload slots and quota bookkeeping, shared by batch mode (Mac renders + uploads) and the Pi
uploader. No rendering imports here, so the Pi only needs the Google API libraries."""
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH_ROOT = os.path.join(ROOT, "channels")
UTC = dt.timezone.utc


def load(path, default):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return default


def config():
    return load(os.path.join(ROOT, "schedule.json"), {})


def longform_hours():
    hours = {}
    p = os.path.join(ROOT, "longform.txt")
    for line in open(p) if os.path.exists(p) else []:
        line = line.split("#")[0].strip()
        if ":" in line:
            c, h = (x.strip() for x in line.split(":", 1))
            if c and h.isdigit():
                hours[c] = [int(h)]
    return hours


def plans(cfg):
    """[(kind, slug, [utc hours])] for every active channel."""
    return [("short", s, hs) for s, hs in cfg.get("shorts", {}).items()] + \
           [("long", s, hs) for s, hs in longform_hours().items()]


def filled():
    """Latest scheduled_for per 'short-<slug>' / 'long-<slug>' from published scripts in git."""
    out = {}
    for slug in os.listdir(CH_ROOT):
        for kind, sub in (("short", "published"), ("long", os.path.join("longform", "published"))):
            d = os.path.join(CH_ROOT, slug, sub)
            for f in os.listdir(d) if os.path.isdir(d) else []:
                js = load(os.path.join(d, f), {}) if f.endswith(".json") else {}
                at = js.get("scheduled_for") or js.get("published_at")  # older direct uploads
                if at and at > out.get(f"{kind}-{slug}", ""):
                    out[f"{kind}-{slug}"] = at
    return out


def slots(cfg, now, days=None):
    """[(time, kind, slug)] from now+1h up to `days` ahead. Filled day by day; within a day
    long-form first (watch hours), then the priority channel, then time."""
    days = cfg.get("days_ahead", 3) if days is None else days
    out, minute = [], cfg.get("minute", 7)
    soon = now + dt.timedelta(hours=1)  # YouTube needs publishAt in the future; leave processing time
    for d in range(days + 1):
        day = (now + dt.timedelta(days=d)).date()
        for kind, slug, hours in plans(cfg):
            for h in hours:
                t = dt.datetime(day.year, day.month, day.day, h, minute, tzinfo=UTC)
                if soon <= t <= now + dt.timedelta(days=days):
                    out.append((t, kind, slug))
    rank = {s: i for i, s in enumerate(cfg.get("priority", []))}
    return sorted(out, key=lambda x: (x[0].date(), x[1] != "long", rank.get(x[2], 99), x[0]))


class Quota:
    """Uploads used this quota day (YouTube resets at midnight Pacific)."""

    def __init__(self, cfg, name):
        self.path = os.path.join(ROOT, ".state", name)
        self.budget = cfg.get("daily_upload_budget", 6)
        day = dt.datetime.now(UTC).astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
        st = load(self.path, {}).get("quota", {})
        self.used = st.get("used", 0) if st.get("day") == day else 0
        self.day = day

    def left(self):
        return self.budget - self.used

    def spend(self, n=1):
        self.used += n
        self.save()

    def exhaust(self):
        self.used = self.budget
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump({"quota": {"day": self.day, "used": self.used}}, open(self.path, "w"))
