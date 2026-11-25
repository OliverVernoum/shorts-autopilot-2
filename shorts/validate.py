"""Check script JSON files against the format the renderer expects.
Usage: python -m shorts.validate channels/*/queue/*.json channels/*/longform/queue/*.json
Files with a "chapters" key are checked as long-form scripts (check_long).
"""
import json
import sys

KINDS = {"title", "big", "terminal", "steps", "versus", "bars", "quiz", "timeline"}


def check_scene(i, sc):
    """Errors for one scene object (shared by Shorts and long-form)."""
    errs = []
    k = sc.get("kind")
    if k not in KINDS:
        return [f"scene {i}: bad kind {k}"]
    if not sc.get("say"):
        errs.append(f"scene {i}: no say")
    if k in ("title", "big") and not sc.get("big"):
        errs.append(f"scene {i}: needs big")
    if k == "big" and len(sc.get("big", "")) > 18:
        errs.append(f"scene {i}: big text > 18 chars")
    if k == "terminal":
        ls = sc.get("lines", [])
        if not 2 <= len(ls) <= 9 or any(len(l) > 60 for l in ls):
            errs.append(f"scene {i}: terminal needs 2-9 lines <= 60 chars")
    if k == "steps":
        st = sc.get("steps", [])
        if not 2 <= len(st) <= 5 or any(len(x) > 48 for x in st):
            errs.append(f"scene {i}: steps needs 2-5 items <= 48 chars")
    if k == "versus":
        for side in ("left", "right"):
            v = sc.get(side, {})
            if not v.get("label") or not 1 <= len(v.get("items", [])) <= 4 or \
                    any(len(x) > 32 for x in v.get("items", [])):
                errs.append(f"scene {i}: versus.{side} needs label + 1-4 items <= 32 chars")
    if k == "bars":
        bs = sc.get("bars", [])
        ok = isinstance(bs, list) and 2 <= len(bs) <= 5 and all(
            isinstance(b, dict) and 1 <= len(str(b.get("label", ""))) <= 18 and
            isinstance(b.get("value"), (int, float)) and not isinstance(b.get("value"), bool)
            and b["value"] >= 0 for b in bs)
        if not ok:
            errs.append(f"scene {i}: bars needs 2-5 {{label <= 18 chars, value >= 0}}")
        elif max(b["value"] for b in bs) <= 0:
            errs.append(f"scene {i}: bars needs at least one value > 0")
        if len(sc.get("unit", "")) > 8:
            errs.append(f"scene {i}: bars unit > 8 chars")
        if len(sc.get("title", "")) > 30:
            errs.append(f"scene {i}: bars title > 30 chars")
    if k == "quiz":
        q, opts, ans = sc.get("question", ""), sc.get("options", []), sc.get("answer")
        if not q or len(q) > 90:
            errs.append(f"scene {i}: quiz needs question <= 90 chars")
        if not isinstance(opts, list) or not 2 <= len(opts) <= 4 or \
                any(not x or len(x) > 28 for x in opts):
            errs.append(f"scene {i}: quiz needs 2-4 options <= 28 chars")
        elif not isinstance(ans, int) or isinstance(ans, bool) or not 0 <= ans < len(opts):
            errs.append(f"scene {i}: quiz answer must be an option index 0-{len(opts) - 1}")
    if k == "timeline":
        ev = sc.get("events", [])
        if not isinstance(ev, list) or not 3 <= len(ev) <= 5 or any(
                not isinstance(e, dict) or not 1 <= len(str(e.get("year", ""))) <= 10 or
                not 1 <= len(e.get("text", "")) <= 30 for e in ev):
            errs.append(f"scene {i}: timeline needs 3-5 {{year <= 10, text <= 30 chars}}")
    return errs


def check(path):
    errs = []
    s = json.load(open(path))
    for k in ("id", "title", "description", "tags", "scenes", "sources"):
        if k not in s:
            errs.append(f"missing {k}")
    if len(s.get("title", "")) > 90:
        errs.append("title > 90 chars")
    scenes = s.get("scenes", [])
    if not 4 <= len(scenes) <= 8:
        errs.append("need 4-8 scenes")
    if scenes and scenes[0].get("kind") != "title":
        errs.append("first scene must be kind=title")
    words = 0
    prev = None
    for i, sc in enumerate(scenes):
        k = sc.get("kind")
        if k in KINDS and k == prev:
            errs.append(f"scene {i}: same kind as previous ({k})")
        prev = k
        errs += check_scene(i, sc)
        words += len(sc.get("say", "").split())
    if not 95 <= words <= 170:
        errs.append(f"narration is {words} words (want 95-170, ~40-60s)")
    return errs


def check_long(path):
    """Long-form script: {id, title, description, tags, sources, thumb_text?, thumb_highlight?,
    chapters: [{title, scenes: [<Shorts scene>, ...]}]} -> 5-8 chapters, 900-1500 words."""
    errs = []
    try:
        s = json.load(open(path))
    except Exception as e:
        return [f"not valid JSON: {e}"]
    for k in ("id", "title", "description", "tags", "sources", "chapters"):
        if k not in s:
            errs.append(f"missing {k}")
    if errs:
        return errs
    if not s["title"] or len(s["title"]) > 90:
        errs.append("title must be 1-90 chars")
    if not s["description"]:
        errs.append("empty description")
    if not isinstance(s["tags"], list):
        errs.append("tags must be a list")
    if not isinstance(s["sources"], list) or not s["sources"]:
        errs.append("sources must be a non-empty list")
    tt = s.get("thumb_text")
    if tt is not None and (not 3 <= len(str(tt).split()) <= 6 or len(str(tt)) > 40):
        errs.append("thumb_text must be 3-6 words, <= 40 chars")
    hl = s.get("thumb_highlight")
    if hl and tt and hl.lower() not in [w.strip(".,!?:;").lower() for w in str(tt).split()]:
        errs.append("thumb_highlight must be one word of thumb_text")
    chapters = s["chapters"]
    if not isinstance(chapters, list) or not 5 <= len(chapters) <= 8:
        return errs + ["need 5-8 chapters"]
    words = 0
    for c, ch in enumerate(chapters):
        if not isinstance(ch, dict) or not 1 <= len(ch.get("title", "")) <= 40:
            errs.append(f"chapter {c}: title must be 1-40 chars")
            continue
        scenes = ch.get("scenes", [])
        if not isinstance(scenes, list) or not 2 <= len(scenes) <= 8:
            errs.append(f"chapter {c}: needs 2-8 scenes")
            continue
        prev = None
        for j, sc in enumerate(scenes):
            label = f"chapter {c} scene {j}"
            k = sc.get("kind")
            if k in KINDS and k == prev:
                errs.append(f"{label}: same kind as previous ({k})")
            prev = k
            errs += [e.replace(f"scene {j}:", f"{label}:", 1) for e in check_scene(j, sc)]
            n = len(sc.get("say", "").split())
            if n > 90:
                errs.append(f"{label}: say is {n} words (max 90, split it so the visual changes)")
            words += n
    if not 900 <= words <= 1500:
        errs.append(f"narration is {words} words (want 900-1500, ~5-10 min)")
    return errs


def check_any(path):
    try:
        long = "chapters" in json.load(open(path))
    except Exception as e:
        return [f"not valid JSON: {e}"]
    return check_long(path) if long else check(path)


if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        e = check_any(p)
        print(("OK   " if not e else "FAIL ") + p + ("" if not e else "\n  - " + "\n  - ".join(e)))
        bad += bool(e)
    sys.exit(1 if bad else 0)
