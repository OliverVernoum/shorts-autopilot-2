"""Pull recent viewer comments for each channel into channels/<slug>/feedback/comments.json
so the script writers can act on them (complaints, requests, topic ideas).

  python -m shorts.comments [--channel gaming]

Uses the channel's OAuth token; if that token's scope can't read comments, set YT_API_KEY
(Google Cloud -> Credentials -> API key, YouTube Data API v3) in shorts.env. Costs ~2 API units.
"Breakaway" comments = the most-liked / most-replied ones, flagged so writers look at them first.
"""
import argparse
import datetime as dt
import json
import os

from . import run, upload


def _yt(slug):
    try:
        return upload.client(slug)
    except BaseException:
        key = os.environ.get("YT_API_KEY")
        if not key:
            raise
        from googleapiclient.discovery import build
        return build("youtube", "v3", developerKey=key, cache_discovery=False)


def fetch(slug, days=30, limit=100):
    yt = _yt(slug)
    me = yt.channels().list(part="id", mine=True).execute() if os.environ.get(
        f"YT_REFRESH_TOKEN_{slug.upper()}") else {}
    cid = (me.get("items") or [{}])[0].get("id") or json.load(
        open(os.path.join(run.CH_ROOT, slug, "channel.json"))).get("channel_id")
    if not cid:
        raise RuntimeError("no channel id")
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out, token = [], None
    while len(out) < limit:
        r = yt.commentThreads().list(part="snippet", allThreadsRelatedToChannelId=cid,
                                     maxResults=100, order="time", textFormat="plainText",
                                     pageToken=token).execute()
        for it in r.get("items", []):
            top = it["snippet"]["topLevelComment"]["snippet"]
            when = dt.datetime.fromisoformat(top["publishedAt"].replace("Z", "+00:00"))
            if when < since:
                token = None
                break
            out.append({"video_id": it["snippet"].get("videoId"), "text": top["textDisplay"][:500],
                        "likes": top.get("likeCount", 0),
                        "replies": it["snippet"].get("totalReplyCount", 0),
                        "at": top["publishedAt"]})
        else:
            token = r.get("nextPageToken")
        if not token:
            break
    titles = {}
    ids = list({c["video_id"] for c in out if c["video_id"]})
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute().get("items", []):
            titles[v["id"]] = v["snippet"]["title"]
    for c in out:
        c["video"] = titles.get(c["video_id"], "")
        c["score"] = c["likes"] + 2 * c["replies"]
    out.sort(key=lambda c: -c["score"])
    cut = max(2, sorted([c["score"] for c in out], reverse=True)[min(4, len(out) - 1)]) if out else 0
    for c in out:
        c["breakaway"] = c["score"] >= cut and c["score"] > 0
    d = os.path.join(run.CH_ROOT, slug, "feedback")
    os.makedirs(d, exist_ok=True)
    json.dump({"fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "days": days, "comments": out}, open(os.path.join(d, "comments.json"), "w"),
              indent=2, ensure_ascii=False)
    return len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(run.ROOT, "schedule.json")))
    for slug in ([a.channel] if a.channel else cfg.get("priority") or list(cfg.get("shorts", {}))):
        try:
            print(f"[{slug}] {fetch(slug)} comments saved")
        except Exception as e:
            print(f"::warning::[{slug}] comments not fetched: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    main()
