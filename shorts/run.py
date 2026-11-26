"""Publish the next queued Short for a channel.

  python -m shorts.run --channel cyber            render + upload next script
  python -m shorts.run --channel cyber --dry-run  render only (no upload, queue untouched)
  python -m shorts.run --all                      one Short for every channel folder
  python -m shorts.run --channel cyber --longform next long-form video from
                                                  channels/cyber/longform/queue
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

from . import render, upload, validate

ROOT = render.ROOT
CH_ROOT = os.path.join(ROOT, "channels")


def gh_summary(line):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(line + "\n")
    print(line)


def publish(slug, dry_run=False, tts_mode="edge", publish_at=None):
    ch_dir = os.path.join(CH_ROOT, slug)
    channel = json.load(open(os.path.join(ch_dir, "channel.json")))
    qdir = os.path.join(ch_dir, "queue")
    queue = sorted(f for f in os.listdir(qdir) if f.endswith(".json"))
    if not queue:
        gh_summary(f"::warning::[{slug}] queue empty, nothing to publish")
        return False
    if len(queue) <= 3:
        gh_summary(f"::warning::[{slug}] only {len(queue)} scripts left in queue")
    if not dry_run and not os.environ.get(f"YT_REFRESH_TOKEN_{slug.upper()}"):
        gh_summary(f"::warning::[{slug}] no YT_REFRESH_TOKEN_{slug.upper()} secret yet, skipping")
        return False
    path = os.path.join(qdir, queue[0])
    errs = validate.check(path)
    if errs:
        # park broken scripts so one bad file can't block the channel
        os.makedirs(os.path.join(ch_dir, "rejected"), exist_ok=True)
        shutil.move(path, os.path.join(ch_dir, "rejected", queue[0]))
        gh_summary(f"::error::[{slug}] {queue[0]} failed validation: {errs}")
        return publish(slug, dry_run, tts_mode, publish_at) if len(queue) > 1 else False
    script = json.load(open(path))
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    out = os.path.join(ROOT, "out", f"{slug}-{script['id']}.mp4")
    rend = render.Renderer(script, channel)
    dur = rend.render(out, out + ".work", tts_mode)
    script["credits"] = rend.credits
    shutil.rmtree(out + ".work", ignore_errors=True)
    gh_summary(f"[{slug}] rendered {script['id']} ({dur:.1f}s)")
    if dry_run:
        return True
    vid, privacy = upload.upload(out, script, channel, slug, publish_at=publish_at)
    script.update({"video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
                   "published_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "privacy": privacy})
    if publish_at:
        script["scheduled_for"] = publish_at.isoformat()
    os.makedirs(os.path.join(ch_dir, "published"), exist_ok=True)
    with open(os.path.join(ch_dir, "published", queue[0]), "w") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    os.remove(path)
    gh_summary(f"[{slug}] uploaded **{script['title']}** -> {script['url']} ({privacy})")
    return True


def publish_long(slug, dry_run=False, tts_mode="edge", publish_at=None):
    """Render + upload the next long-form script. Quietly skips channels with no long-form
    queue, an empty queue, or no YouTube token yet."""
    from . import brand, longform
    ch_dir = os.path.join(CH_ROOT, slug)
    lf = os.path.join(ch_dir, "longform")
    qdir = os.path.join(lf, "queue")
    queue = sorted(f for f in os.listdir(qdir) if f.endswith(".json")) if os.path.isdir(qdir) else []
    if not queue:
        gh_summary(f"[{slug}] long-form queue empty, nothing to publish")
        return False
    if not dry_run and not os.environ.get(f"YT_REFRESH_TOKEN_{slug.upper()}"):
        gh_summary(f"[{slug}] no YT_REFRESH_TOKEN_{slug.upper()} secret yet, skipping long-form")
        return False
    channel = json.load(open(os.path.join(ch_dir, "channel.json")))
    path = os.path.join(qdir, queue[0])
    errs = validate.check_long(path)
    if errs:
        os.makedirs(os.path.join(lf, "rejected"), exist_ok=True)
        shutil.move(path, os.path.join(lf, "rejected", queue[0]))
        gh_summary(f"::error::[{slug}] long-form {queue[0]} failed validation: {errs}")
        return publish_long(slug, dry_run, tts_mode, publish_at) if len(queue) > 1 else False
    script = json.load(open(path))
    os.makedirs(os.path.join(ROOT, "out"), exist_ok=True)
    out = os.path.join(ROOT, "out", f"{slug}-{script['id']}.mp4")
    thumb = brand.thumbnail(script, channel, slug, out[:-4] + ".png")
    lr = longform.LongRenderer(script, channel, slug)
    total, starts = lr.render(out, out + ".work", tts_mode)
    script["credits"] = lr.r.credits
    shutil.rmtree(out + ".work", ignore_errors=True)
    chapters = longform.chapter_block(script, starts, total)
    gh_summary(f"[{slug}] rendered long-form {script['id']} ({total / 60:.1f} min)")
    if not chapters:
        gh_summary(f"::warning::[{slug}] chapter timings break YouTube's rules, uploading without")
    if dry_run:
        print(chapters or "")
        return True
    vid, privacy = upload.upload(out, script, channel, slug, extra=chapters, thumbnail=thumb,
                                 publish_at=publish_at)
    script.update({"video_id": vid, "url": f"https://youtu.be/{vid}",
                   "published_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                   "privacy": privacy, "duration_s": round(total, 1),
                   "chapter_starts": [round(s, 1) for s in starts]})
    if publish_at:
        script["scheduled_for"] = publish_at.isoformat()
    os.makedirs(os.path.join(lf, "published"), exist_ok=True)
    with open(os.path.join(lf, "published", queue[0]), "w") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    os.remove(path)
    gh_summary(f"[{slug}] uploaded long-form **{script['title']}** -> {script['url']} ({privacy})")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tts", default="edge", choices=["edge", "silent"])
    ap.add_argument("--count", type=int, default=1, help="Shorts per channel this run")
    ap.add_argument("--longform", action="store_true",
                    help="publish from channels/<slug>/longform/queue instead (16:9, 5-10 min)")
    ap.add_argument("--batch", action="store_true",
                    help="render + upload ahead of time with YouTube scheduled publishing (schedule.json)")
    ap.add_argument("--showcase", metavar="SCRIPT",
                    help="render SCRIPT and upload it UNLISTED to --channel (queue untouched)")
    ap.add_argument("--render-ahead", action="store_true",
                    help="render ahead and ship to the Pi (schedule.json pi_host); no uploads")
    a = ap.parse_args()
    if a.render_ahead:
        from . import ahead
        sys.exit(ahead.main(tts_mode=a.tts))
    if a.showcase:
        ch_dir = os.path.join(CH_ROOT, a.channel)
        channel = dict(json.load(open(os.path.join(ch_dir, "channel.json"))), privacy="unlisted")
        script = json.load(open(a.showcase))
        out = os.path.join(ROOT, "out", f"{a.channel}-{script['id']}.mp4")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        rend = render.Renderer(script, channel)
        dur = rend.render(out, out + ".work", a.tts)
        script["credits"] = rend.credits
        print(f"rendered {out} ({dur:.1f}s); media: {rend.credits or 'none found'}")
        if not a.dry_run:
            vid, privacy = upload.upload(out, script, channel, a.channel)
            print(f"UPLOADED ({privacy}): https://youtube.com/shorts/{vid}")
        sys.exit(0)
    if a.batch:
        from . import batch
        sys.exit(batch.main(dry_run=a.dry_run, tts_mode=a.tts))
    pub = publish_long if a.longform else publish
    slugs = sorted(os.listdir(CH_ROOT)) if a.all else [c.strip() for c in a.channel.split(",")]
    failed = []
    for s in slugs:
        try:
            for _ in range(a.count):
                if not pub(s, a.dry_run, a.tts):
                    break
        except Exception as e:  # keep other channels going
            gh_summary(f"::error::[{s}] {type(e).__name__}: {e}")
            failed.append(s)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
