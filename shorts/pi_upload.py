"""Pi side of the Mac-renders / Pi-uploads split. Needs only the Google API libraries.

  python -m shorts.pi_upload

Every hour: fill empty slots in the next `days_ahead` days with videos the Mac shipped to
`pi_dir` (default ~/shorts-ready), uploaded as private + publishAt so YouTube publishes them on
time. Long-form first, then the priority channel; at most `daily_upload_budget` uploads a quota
day. After each upload the script moves rendered/ -> published/ in git (with video id and slot)
and the local video is deleted.
"""
import datetime as dt
import glob
import json
import os
import sys

from . import slots, upload


def _say(line):
    print(line, flush=True)


def ready_dir(cfg):
    return os.path.expanduser(cfg.get("pi_dir_local") or os.path.join("~", cfg.get("pi_dir", "shorts-ready")))


def next_ready(rd, kind, slug):
    vids = sorted(glob.glob(os.path.join(rd, f"{kind}__{slug}__*.mp4")))
    for v in vids:
        if os.path.exists(v[:-4] + ".json"):
            return v
    return None


def publish_one(rd, video, t):
    meta = json.load(open(video[:-4] + ".json"))
    kind, slug = meta["kind"], meta["slug"]
    channel = json.load(open(os.path.join(slots.CH_ROOT, slug, "channel.json")))
    thumb = os.path.join(rd, meta["thumbnail"]) if meta.get("thumbnail") else None
    vid, privacy = upload.upload(video, meta, channel, slug, extra=meta.get("chapters_text"),
                                 thumbnail=thumb if thumb and os.path.exists(thumb) else None,
                                 publish_at=t)
    short = kind == "short"
    meta.update(video_id=vid, url=f"https://youtube.com/shorts/{vid}" if short else f"https://youtu.be/{vid}",
                privacy=privacy, scheduled_for=t.isoformat(),
                published_at=dt.datetime.now(slots.UTC).isoformat(timespec="seconds"))
    base = os.path.join(slots.CH_ROOT, slug, "" if short else "longform")
    name = meta["id"] + ".json"
    for f in glob.glob(os.path.join(base, "rendered", meta["id"] + "*.json")):
        name = os.path.basename(f)
        os.remove(f)
    os.makedirs(os.path.join(base, "published"), exist_ok=True)
    for k in ("kind", "slug", "thumbnail", "chapters_text"):
        meta.pop(k, None)
    json.dump(meta, open(os.path.join(base, "published", name), "w"), indent=2, ensure_ascii=False)
    for f in (video, video[:-4] + ".json", thumb):
        if f and os.path.exists(f):
            os.remove(f)
    _say(f"[{slug}] scheduled {kind} '{meta['title']}' for {t:%a %d %b %H:%M}Z -> {meta['url']}")


def main():
    cfg = slots.config()
    rd = ready_dir(cfg)
    os.makedirs(rd, exist_ok=True)
    quota = slots.Quota(cfg, "pi-upload.json")
    now = dt.datetime.now(slots.UTC)
    filled = slots.filled()
    empty, failed = set(), False
    for t, kind, slug in slots.slots(cfg, now):
        key = f"{kind}-{slug}"
        last = filled.get(key)
        if key in empty or (last and dt.datetime.fromisoformat(last) >= t):
            continue
        if quota.left() <= 0:
            _say(f"daily upload budget ({quota.budget}) used; next run carries on")
            break
        video = next_ready(rd, kind, slug)
        if not video:
            empty.add(key)
            continue
        try:
            publish_one(rd, video, t)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            _say(f"::error::[{slug}] {kind} for {t:%a %H:%M}Z: {msg[:300]}")
            failed = True
            if "quota" in msg.lower():
                quota.exhaust()
                break
            empty.add(key)
            continue
        filled[key] = t.isoformat()
        quota.spend()
    waiting = len(glob.glob(os.path.join(rd, "*.mp4")))
    _say(f"uploads today {quota.used}/{quota.budget}; {waiting} videos waiting on the Pi; "
         f"scheduled up to: {json.dumps(dict(sorted(filled.items())))}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
