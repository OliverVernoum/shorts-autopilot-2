"""Fetch real, licence-safe photos for `photo` scenes (Wikimedia Commons).

  fetch(query) -> (path, credit) or None   (cached in media_cache/, never raises)

Only CC0 / public domain / CC BY / CC BY-SA images are used. The credit string must go in the
video description (run.py does this) because CC BY needs attribution.
"""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "media_cache")
API = "https://commons.wikimedia.org/w/api.php"
UA = "shorts-autopilot/1.0 (https://github.com/OliverVernoum/shorts-autopilot-2)"
OK_LICENCE = re.compile(r"^(cc0|pd|public domain|cc[ -]by(?!-nc)(?!-nd)|cc-by-sa)", re.I)
OK_MIME = {"image/jpeg", "image/png"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _strip(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _search(query):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": query, "gsrlimit": 12, "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 1200,
    }
    data = json.loads(_get(API + "?" + urllib.parse.urlencode(params)))
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for pg in pages:
        info = (pg.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if info.get("mime") not in OK_MIME or not OK_LICENCE.match(lic):
            continue
        if info.get("width", 0) < 800 or info.get("height", 0) < 500:
            continue
        who = _strip(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons"
        credit = f"{who[:60]} / {lic} / Wikimedia Commons"
        return info.get("thumburl") or info["url"], credit
    return None


def fetch(query):
    try:
        os.makedirs(CACHE, exist_ok=True)
        key = hashlib.md5(query.lower().encode()).hexdigest()[:16]
        img, meta = os.path.join(CACHE, key + ".jpg"), os.path.join(CACHE, key + ".json")
        if os.path.exists(img) and os.path.exists(meta):
            return img, json.load(open(meta))["credit"]
        hit = _search(query)
        if not hit:
            return None
        url, credit = hit
        with open(img, "wb") as f:
            f.write(_get(url, 40))
        json.dump({"credit": credit, "query": query, "url": url}, open(meta, "w"))
        return img, credit
    except Exception as e:  # network or API trouble must never break a render
        print(f"[media] {query!r}: {e}")
        return None


VIDEO_MIME = {"video/webm", "application/ogg", "video/ogg", "video/mp4", "image/gif"}


def _search_clip(query):
    params = {
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"filetype:video {query}", "gsrlimit": 12, "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
    }
    data = json.loads(_get(API + "?" + urllib.parse.urlencode(params)))
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for pg in pages:
        info = (pg.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if info.get("mime") not in VIDEO_MIME or not OK_LICENCE.match(lic):
            continue
        if info.get("size", 0) > 40_000_000:
            continue
        who = _strip(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons"
        return info["url"], f"{who[:60]} / {lic} / Wikimedia Commons"
    return None


def fetch_clip(query):
    """-> (video_path, credit) or None. Licence-safe clip from Commons, cached, never raises."""
    try:
        os.makedirs(CACHE, exist_ok=True)
        key = "v" + hashlib.md5(query.lower().encode()).hexdigest()[:15]
        meta = os.path.join(CACHE, key + ".json")
        if os.path.exists(meta):
            m = json.load(open(meta))
            if os.path.exists(m["path"]):
                return m["path"], m["credit"]
        hit = _search_clip(query)
        if not hit:
            return None
        url, credit = hit
        path = os.path.join(CACHE, key + os.path.splitext(url)[1].lower())
        with open(path, "wb") as f:
            f.write(_get(url, 90))
        json.dump({"credit": credit, "query": query, "url": url, "path": path}, open(meta, "w"))
        return path, credit
    except Exception as e:
        print(f"[media] clip {query!r}: {e}")
        return None


# ---------- current-game footage ----------
# Order: 1) Steam store trailers (official, publisher-supplied, no key needed, PC games),
#        2) yt-dlp on the official trailer (any platform; needs `pip install yt-dlp`).
# Both are short transformative clips for commentary/education; some publishers (e.g. Nintendo)
# still issue Content ID claims, so keep clips short and always credit the publisher.
STEAM_SEARCH = "https://store.steampowered.com/api/storesearch/?cc=us&l=en&term="
STEAM_APP = "https://store.steampowered.com/api/appdetails?cc=us&l=en&appids="


def _steam(query):
    items = json.loads(_get(STEAM_SEARCH + urllib.parse.quote(query))).get("items", [])
    if not items:
        return None
    app = items[0]
    data = json.loads(_get(STEAM_APP + str(app["id"]))).get(str(app["id"]), {})
    d = data.get("data") if data.get("success") else None
    if not d or not d.get("movies"):
        return None
    mv = d["movies"][0]
    url = (mv.get("mp4") or {}).get("max") or (mv.get("mp4") or {}).get("480") or \
        (mv.get("webm") or {}).get("max") or (mv.get("webm") or {}).get("480")
    if not url:
        return None
    pub = ", ".join(d.get("publishers") or []) or "the publisher"
    return url, f'Footage: {d.get("name", app["name"])} trailer, (c) {pub}, via Steam', 6


def _ytdlp(query, out_base):
    import shutil
    import subprocess
    if not shutil.which("yt-dlp"):
        return None
    r = subprocess.run(
        ["yt-dlp", "-q", "--no-playlist", "--max-filesize", "80M", "-f", "mp4/bestvideo[height<=720]",
         "--match-filter", "duration < 400", "-o", out_base + ".%(ext)s",
         "--print", "after_move:%(filepath)s|||%(channel)s|||%(title)s",
         f"ytsearch1:{query} official gameplay trailer"],
        capture_output=True, text=True, timeout=180)
    line = (r.stdout or "").strip().splitlines()[-1:] or [""]
    if r.returncode != 0 or "|||" not in line[0]:
        return None
    path, chan, title = line[0].split("|||", 2)
    return path, f"Footage: {title[:50]} / {chan} (official trailer, via YouTube)", 6


def fetch_game(query):
    """-> (video_path, credit, start_seconds) for a current game, or None. Never raises."""
    try:
        os.makedirs(CACHE, exist_ok=True)
        key = "g" + hashlib.md5(query.lower().encode()).hexdigest()[:15]
        meta = os.path.join(CACHE, key + ".json")
        if os.path.exists(meta):
            m = json.load(open(meta))
            if os.path.exists(m["path"]):
                return m["path"], m["credit"], m["ss"]
        for finder in (_steam, _ytdlp):
            try:
                if finder is _steam:
                    hit = _steam(query)
                    if hit:
                        url, credit, ss = hit
                        path = os.path.join(CACHE, key + os.path.splitext(url.split("?")[0])[1])
                        with open(path, "wb") as f:
                            f.write(_get(url, 120))
                else:
                    hit = _ytdlp(query, os.path.join(CACHE, key))
                    if hit:
                        path, credit, ss = hit
            except Exception as e:
                print(f"[media] game {query!r} via {finder.__name__}: {e}")
                hit = None
            if hit:
                json.dump({"credit": credit, "query": query, "path": path, "ss": ss}, open(meta, "w"))
                return path, credit, ss
        return None
    except Exception as e:
        print(f"[media] game {query!r}: {e}")
        return None
