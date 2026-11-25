"""Text-to-speech with word timings.

Primary: edge-tts (free Microsoft neural voices, gives exact word boundaries).
Fallback: silent audio with estimated timings (used for local previews or if TTS is down
and ALLOW_SILENT=1).
"""
import asyncio
import os
import re
import subprocess
import time


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def estimate_words(text, wpm=170, start=0.0):
    """Rough per-word timings, weighted by word length."""
    words = text.split()
    weights = [max(2, len(re.sub(r"\W", "", w))) + (3 if re.search(r"[.,!?;:]$", w) else 0)
               for w in words]
    total = len(words) / wpm * 60
    per = total / sum(weights)
    t, out = start, []
    for w, k in zip(words, weights):
        d = k * per
        out.append({"word": w, "start": t, "end": t + d * 0.92})
        t += d
    return out, total


async def _edge(text, voice, rate, mp3_path):
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append({"word": chunk["text"], "start": s, "end": s + chunk["duration"] / 1e7})
    return words


def synth_scene(text, voice, rate, mp3_path, mode="edge"):
    """Returns (words, duration). Word times are relative to the start of this clip."""
    if mode == "edge":
        last = None
        for attempt in range(4):
            try:
                words = asyncio.run(_edge(text, voice, rate, mp3_path))
                if words and os.path.getsize(mp3_path) > 1000:
                    return _align_punct(text, words), _probe_duration(mp3_path)
            except Exception as e:  # network hiccups / throttling
                last = e
            time.sleep(3 * (attempt + 1))
        if os.environ.get("ALLOW_SILENT") != "1":
            raise RuntimeError(f"edge-tts failed: {last}")
    words, dur = estimate_words(text)
    dur += 0.2
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", f"{dur:.3f}", "-q:a", "9", mp3_path],
                   check=True)
    return words, dur


def _align_punct(text, words):
    """edge-tts strips punctuation from boundary words; reattach it from the source text so
    captions keep commas/full stops."""
    src = text.split()
    i = 0
    for w in words:
        bare = re.sub(r"\W", "", w["word"]).lower()
        for j in range(i, min(i + 4, len(src))):
            if re.sub(r"\W", "", src[j]).lower() == bare:
                w["word"] = src[j]
                i = j + 1
                break
    return words
