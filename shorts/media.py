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
