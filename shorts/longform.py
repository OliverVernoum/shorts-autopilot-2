"""Render a long-form script (5-10 min, 1920x1080, 30 fps) from chapters of Shorts scenes.

Script: channels/<slug>/longform/queue/<id>.json
  {id, title, description, tags, sources, thumb_text?, thumb_highlight?,
   chapters: [{title, scenes: [<Shorts scene>, ...]}, ...]}      (checked by validate.check_long)

Layout:
  top     chapter label (number + title), channel name, segmented progress bar (one per chapter)
  middle  the Shorts scene visuals, drawn by render.Renderer on a wide virtual canvas and scaled in
  bottom  word-highlighted captions
Each chapter opens with a full-screen card in the channel's branding style (shorts/brand.py).
Frames are rendered in parallel segments and joined with ffmpeg's concat demuxer.

Local preview:
  python -m shorts.longform channels/cyber/longform/queue/L001-x.json /tmp/L001.mp4 [silent]
"""
import json
import math
import multiprocessing as mp
import os
import subprocess
import sys
import time
import wave

import numpy as np
from PIL import Image, ImageDraw

from . import brand, render
from .render import BODY, HEAD, MONO, Renderer, ease_out, font, text_img

LW, LH, FPS = 1920, 1080, 30
CARD = 2.6                      # seconds each chapter card holds before narration starts
VW = 1900                       # virtual canvas width the Shorts scene layouts are drawn on
VY0, VY1 = 320, 1190            # band of the virtual canvas that holds scene visuals
VIS_H = 720                     # its height in the final frame...
VIS_Y = 108                     # ...and where it sits
VIS_W = int(VW * VIS_H / (VY1 - VY0))
VIS_X = (LW - VIS_W) // 2
CAP_Y = 872                     # caption line (top of text)
BAR = (60, LW - 60, 80, 8)      # progress bar x0, x1, y, gap between chapter segments
KICK = {"cyber": "CHAPTER", "gaming": "LEVEL", "tech": "SECTION"}


def flatten(script):
    scenes, chapter_of = [], []
    for ci, ch in enumerate(script["chapters"]):
        for sc in ch["scenes"]:
            scenes.append(sc)
            chapter_of.append(ci)
    return scenes, chapter_of


def timestamp(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapter_block(script, starts, total):
    """YouTube chapter list, or None if it breaks YouTube's rules (first 0:00, >= 3, each >= 10s)."""
    ends = list(starts[1:]) + [total]
    if len(starts) < 3 or starts[0] != 0 or any(e - s < 10 for s, e in zip(starts, ends)):
        return None
    lines = [f"{timestamp(st)} {ch['title']}" for ch, st in zip(script["chapters"], starts)]
    return "Chapters\n" + "\n".join(lines)


class LongRenderer:
    def __init__(self, script, channel, slug):
        self.script = script
        self.slug = slug
        self.ch = channel
        scenes, self.chapter_of = flatten(script)
        self.r = Renderer(dict(script, scenes=scenes), channel, width=VW)
        self.pal = self.r.pal
        self.first_scene = [self.chapter_of.index(c) for c in range(len(script["chapters"]))]
        self.bg = self._background()
        n = len(script["chapters"])
        kick = KICK.get(slug, "CHAPTER")
        self.cards = [brand.card(slug, LW, LH, f"{kick} {i + 1:02d} / {n:02d}", ch["title"],
                                 channel=channel).convert("RGBA")
                      for i, ch in enumerate(script["chapters"])]
        rng = self.r.rng
        glyphs = channel.get("glyphs", "01{}<>#$/\\:;")
        self.particles = [(20 + rng.random() * (LW - 60), rng.random() * LH, rng.uniform(8, 24),
                           rng.choice(glyphs)) for _ in range(26)]

    # ---------- static layers ----------
    def _background(self):
        a, b = np.array(self.pal[0], float), np.array(self.pal[1], float)
        t = np.linspace(0, 1, LH)[:, None, None]
        img = Image.fromarray(np.broadcast_to(a * (1 - t) + b * t, (LH, LW, 3)).astype(np.uint8))
        img = img.convert("RGBA")
        grid = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
        d = ImageDraw.Draw(grid)
        for x in range(0, LW, 80):
            d.line([(x, 0), (x, LH)], fill=(*self.pal[2], 12))
        for y in range(0, LH, 80):
            d.line([(0, y), (LW, y)], fill=(*self.pal[2], 12))
        img.alpha_composite(grid)
        return img

    def _segments(self):
        x0, x1, y, gap = BAR
        n = len(self.starts)
        seg_w = (x1 - x0 - gap * (n - 1)) / n
        return [(x0 + c * (seg_w + gap), seg_w) for c in range(n)], y

    def _track(self):
        """Unfilled progress segments, baked into the background once timings are known."""
        layer = Image.new("RGBA", (LW, LH), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        segs, y = self._segments()
        for sx, sw in segs:
            d.rectangle([sx, y, sx + sw, y + 6], fill=(255, 255, 255, 46))
        self.bg.alpha_composite(layer)

    # ---------- timing ----------
    def prepare(self, workdir, mode):
        lead = {i: CARD for i in self.first_scene}
        audio, timeline, words, total = self.r.build_audio(workdir, mode, lead)
        self.timeline, self.words, self.total = timeline, words, total
        self.starts = [0.0 if c == 0 else round(timeline[i][0] - CARD, 3)
                       for c, i in enumerate(self.first_scene)]
        self._chime(audio)
        self._track()
        return audio

    def _chime(self, path):
        """Soft two-note blip as each chapter card lands (synthesised, no licensed audio)."""
        with wave.open(path) as wf:
            sr = wf.getframerate()
            data = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
        data = data.copy()
        for st in self.starts:
            for k, f0 in enumerate((660.0, 990.0)):
                n = int(0.22 * sr)
                tt = np.arange(n) / sr
                tone = np.sin(2 * math.pi * f0 * tt) * np.exp(-tt * 14) * 0.16
                a = int((st + 0.12 + k * 0.14) * sr)
                seg = data[a:a + n]
                seg += tone[:len(seg)]
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes((np.clip(data, -1, 1) * 32767).astype(np.int16).tobytes())

    def chapter_at(self, t):
        ci = 0
        for c, st in enumerate(self.starts):
            if t >= st:
                ci = c
        return ci

    # ---------- drawing ----------
    def chrome(self, frame, t, ci):
        d = ImageDraw.Draw(frame)
        segs, y = self._segments()
        ends = list(self.starts[1:]) + [self.total]
        for c, (sx, sw) in enumerate(segs):
            p = min(max((t - self.starts[c]) / max(ends[c] - self.starts[c], 0.1), 0), 1)
            if p > 0:
                d.rectangle([sx, y, sx + sw * p, y + 6], fill=self.pal[2])
        num = text_img(f"{ci + 1:02d}", HEAD, 40, (*self.pal[2], 255))
        frame.alpha_composite(num, (60, 26))
        title = self.script["chapters"][ci]["title"]
        lab = text_img(title, BODY, 28, (255, 255, 255, 230))
        frame.alpha_composite(lab, (60 + num.width + 16, 26 + (num.height - lab.height) // 2 + 1))
        name = text_img(self.ch["name"], BODY, 26, (*self.pal[2], 220))
        frame.alpha_composite(name, (LW - 60 - name.width, 26 + (num.height - name.height) // 2 + 1))

    def particles_at(self, frame, t):
        for (x, y, sp, ch) in self.particles:
            yy = 110 + (y - t * sp) % (LH - 140)
            frame.alpha_composite(text_img(ch, MONO, 22, (*self.pal[2], 60)), (int(x), int(yy)))

    def card_frame(self, ci, t):
        """Chapter card with a short per-channel entrance."""
        card = self.cards[ci]
        k = (t - self.starts[ci]) / 0.45
        if k >= 1:
            return card.copy()
        frame = self.bg.copy()
        e = ease_out(k)
        if self.slug == "gaming":       # stepped wipe, like old tile-based screen transitions
            w = int(LW * math.ceil(max(k, 0) * 8) / 8)
            if w > 0:
                frame.alpha_composite(card.crop((0, 0, w, LH)), (0, 0))
        elif self.slug == "cyber":      # paper feeding up out of the printer
            frame.alpha_composite(card, (0, int(LH * (1 - e))))
        else:                           # left-to-right wipe
            w = int(LW * e)
            if w > 0:
                frame.alpha_composite(card.crop((0, 0, w, LH)), (0, 0))
        return frame

    def frame_at(self, t):
        ci = self.chapter_at(t)
        first = self.first_scene[ci]
        if t < self.timeline[first][0] - 0.08:      # card window before the chapter's narration
            return self.card_frame(ci, t)
        frame = self.bg.copy()
        layer = Image.new("RGBA", (VW, VY1), (0, 0, 0, 0))
        idx = max(self.r.scene_index(t, self.timeline), first)
        self.r.draw_scene(layer, idx, t, self.timeline)
        vis = layer.crop((0, VY0, VW, VY1)).resize((VIS_W, VIS_H), Image.BILINEAR)
        frame.alpha_composite(vis, (VIS_X, VIS_Y))
        self.chrome(frame, t, ci)
        self.r.captions(frame, self.words, t, y=CAP_Y, size=62, max_w=LW - 360, max_words=7,
                        max_chars=40, min_size=40)
        return frame

    # ---------- output ----------
    def render(self, out_path, workdir, mode="edge", jobs=None):
        """Returns (total_seconds, chapter_start_seconds)."""
        os.makedirs(workdir, exist_ok=True)
        audio = self.prepare(workdir, mode)
        n = int(self.total * FPS)
        jobs = jobs or int(os.environ.get("RENDER_JOBS", 0)) or max(1, min(os.cpu_count() or 1, 8))
        bounds = [n * k // jobs for k in range(jobs + 1)]
        segs = [os.path.join(workdir, f"seg{k}.mp4") for k in range(jobs)]
        global _JOB
        _JOB = self
        tasks = [(bounds[k], bounds[k + 1], segs[k]) for k in range(jobs)]
        if jobs == 1:
            _segment(tasks[0])
        else:
            with mp.get_context("fork").Pool(jobs) as pool:
                pool.map(_segment, tasks)
        lst = os.path.join(workdir, "segments.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{s}'\n" for s in segs)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", lst, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                        out_path], check=True)
        return self.total, self.starts


_JOB = None


def _segment(task):
    a, b, path = task
    job = _JOB
    threads = "2" if (os.cpu_count() or 1) > 2 else "1"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{LW}x{LH}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-threads", threads, path],
        stdin=subprocess.PIPE)
    for fi in range(a, b):
        proc.stdin.write(job.frame_at(fi / FPS).convert("RGB").tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")


def main():
    """python -m shorts.longform <script.json> <out.mp4> [edge|silent]
    The channel is the folder three levels above the script (channels/<slug>/longform/queue/x.json).
    Also writes <out>.png (thumbnail) and prints the chapter list."""
    script_path, out = sys.argv[1], sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "edge"
    ch_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(script_path))))
    slug = os.path.basename(ch_dir)
    with open(os.path.join(ch_dir, "channel.json")) as f:
        channel = json.load(f)
    with open(script_path) as f:
        script = json.load(f)
    t0 = time.time()
    thumb = brand.thumbnail(script, channel, slug, os.path.splitext(out)[0] + ".png")
    total, starts = LongRenderer(script, channel, slug).render(out, out + ".work", mode)
    print(f"rendered {out} ({total / 60:.1f} min video) in {time.time() - t0:.0f}s; thumbnail {thumb}")
    print(chapter_block(script, starts, total) or "chapters: not valid for YouTube")


if __name__ == "__main__":
    main()
