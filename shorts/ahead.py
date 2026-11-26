"""Mac side of the Mac-renders / Pi-uploads split.

  python -m shorts.run --render-ahead

Renders queued scripts ahead of time and ships them to the Pi, which uploads them on schedule
(shorts/pi_upload.py). Keeps `render_days_ahead` days of videos per channel in flight:
  - finished video + sidecar JSON (script, credits, chapters, thumbnail) -> out/ready/
  - the script moves queue/ -> rendered/ in git, so nothing renders twice
  - out/ready/ is copied to the Pi with rsync over SSH and removed locally once it's there
    (if the Pi is off, files wait in out/ready/ and go next run)
Long-form renders first, then the priority channel. Stops after `max_render_minutes` so an
hourly run never overlaps the next.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import time

from . import render, run, slots, validate

READY = os.path.join(slots.ROOT, "out", "ready")


def _dirs(kind, slug):
    base = os.path.join(slots.CH_ROOT, slug, "longform" if kind == "long" else "")
    return {k: os.path.join(base, k) for k in ("queue", "rendered", "rejected")}


def in_flight(kind, slug):
    d = _dirs(kind, slug)["rendered"]
    return len([f for f in os.listdir(d) if f.endswith(".json")]) if os.path.isdir(d) else 0


def target(cfg, kind, slug):
    hours = dict(((k, s), h) for k, s, h in slots.plans(cfg)).get((kind, slug), [])
    return len(hours) * cfg.get("render_days_ahead", 7)


def render_next(kind, slug, tts_mode="edge"):
    """Render the next valid queued script into out/ready/. True if one was rendered."""
    d = _dirs(kind, slug)
    queue = sorted(f for f in os.listdir(d["queue"]) if f.endswith(".json")) \
        if os.path.isdir(d["queue"]) else []
    check = validate.check_long if kind == "long" else validate.check
    for name in queue:
        path = os.path.join(d["queue"], name)
        errs = check(path)
        if errs:
            os.makedirs(d["rejected"], exist_ok=True)
            shutil.move(path, os.path.join(d["rejected"], name))
            run.gh_summary(f"::error::[{slug}] {kind} {name} failed validation: {errs}")
            continue
        channel = json.load(open(os.path.join(slots.CH_ROOT, slug, "channel.json")))
        script = json.load(open(path))
        os.makedirs(READY, exist_ok=True)
        base = os.path.join(READY, f"{kind}__{slug}__{script['id']}")
        work = base + ".work"
        if kind == "long":
            from . import brand, longform
            thumb = brand.thumbnail(script, channel, slug, base + ".thumb.png")
            lr = longform.LongRenderer(script, channel, slug)
            total, starts = lr.render(base + ".part.mp4", work, tts_mode)
            script["credits"] = lr.r.credits
            script["chapters_text"] = longform.chapter_block(script, starts, total)
            script["thumbnail"] = os.path.basename(thumb)
            script["duration_s"] = round(total, 1)
            script["chapter_starts"] = [round(s, 1) for s in starts]
        else:
            rend = render.Renderer(script, channel)
            total = rend.render(base + ".part.mp4", work, tts_mode)
            script["credits"] = rend.credits
        shutil.rmtree(work, ignore_errors=True)
        script.update(kind=kind, slug=slug, rendered_at=dt.datetime.now(slots.UTC).isoformat(timespec="seconds"))
        json.dump(script, open(base + ".json", "w"), indent=2, ensure_ascii=False)
        os.replace(base + ".part.mp4", base + ".mp4")  # .json first, .mp4 last = "ready"
        os.makedirs(d["rendered"], exist_ok=True)
        shutil.move(path, os.path.join(d["rendered"], name))
        run.gh_summary(f"[{slug}] rendered {kind} {script['id']} ({total:.0f}s) for the Pi")
        return True
    return False


def ship(cfg):
    """rsync out/ready/ to the Pi, deleting local copies that arrived. Videos last."""
    host = cfg.get("pi_host")
    if not host or not os.path.isdir(READY):
        return
    dest = f"{host}:{cfg.get('pi_dir', 'shorts-ready')}/"
    ssh = "ssh -o BatchMode=yes -o ConnectTimeout=10"
    base = ["rsync", "-a", "--partial", "--remove-source-files", "-e", ssh, "--exclude", "*.work",
            "--exclude", "*.part.mp4"]
    for pat in (["--include", "*.json", "--include", "*.png", "--exclude", "*"], []):
        r = subprocess.run(base + pat + [READY + "/", dest], capture_output=True, text=True)
        if r.returncode != 0:
            run.gh_summary(f"::warning::couldn't reach the Pi ({host}); videos wait in out/ready: "
                           f"{r.stderr.strip()[:200]}")
            return
    left = [f for f in os.listdir(READY) if f.endswith(".mp4")]
    run.gh_summary(f"shipped to {host}" + (f" ({len(left)} still local)" if left else ""))


def main(tts_mode="edge"):
    cfg = slots.config()
    deadline = time.time() + 60 * cfg.get("max_render_minutes", 50)
    rank = {s: i for i, s in enumerate(cfg.get("priority", []))}
    order = sorted(((k, s) for k, s, _ in slots.plans(cfg)), key=lambda x: (x[0] != "long", rank.get(x[1], 99)))
    ship(cfg)  # anything left from last time first
    progress = True
    while progress and time.time() < deadline:
        progress = False
        for kind, slug in order:  # one per channel per round, so buffers fill evenly
            if time.time() >= deadline:
                break
            if in_flight(kind, slug) >= target(cfg, kind, slug):
                continue
            try:
                if render_next(kind, slug, tts_mode):
                    progress = True
                    ship(cfg)
            except Exception as e:
                run.gh_summary(f"::error::[{slug}] {kind} render failed: {type(e).__name__}: {str(e)[:200]}")
    run.gh_summary("in flight: " + ", ".join(f"{k}-{s} {in_flight(k, s)}/{target(cfg, k, s)}"
                                             for k, s in order))
    return 0
