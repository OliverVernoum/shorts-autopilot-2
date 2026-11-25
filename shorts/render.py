"""Render a script JSON into a 1080x1920 YouTube Short.

Scene kinds (vary them per video, YouTube penalises same-template spam):
  title    : {"big": "HOOK TEXT", "sub": "optional"}
  big      : {"big": "0.3s", "sub": "to crack 'password123'"}
  terminal : {"lines": ["$ whois evil.com", "> Registered 2 days ago"]}
  steps    : {"steps": ["Recon", "Phish", "Payload"]}
  versus   : {"left": {"label": "Myth", "items": [...]}, "right": {"label": "Fact", "items": [...]}}
  bars     : {"bars": [{"label": "Phishing", "value": 36}, ...], "unit": "%", "title": "Breach causes"}
             2-5 bars, label <= 18 chars, value >= 0; unit (<= 8 chars) and title (<= 30) optional.
             Bars grow in turn, values count up, longest bar = full width.
  quiz     : {"question": "Which is safest?", "options": ["SMS code", "Passkey", "Email link"], "answer": 1}
             2-4 options <= 28 chars, question <= 90 chars, answer = 0-based index.
             Correct option is revealed ~60% through the scene, so ask in "say" then answer.
  timeline : {"events": [{"year": "1998", "text": "First worm spreads"}, ...]}
             3-5 events top to bottom, year <= 10 chars, text <= 30 chars.
Every scene also has "say": the narration.
"""
import functools
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import tts

W, H, FPS = 1080, 1920, 30
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "fonts")
GAP = 0.18  # silence between scenes (s)

PALETTES = [  # bg_top, bg_bottom, accent, accent2
    ((6, 10, 22), (10, 32, 40), (0, 255, 156), (0, 190, 255)),     # terminal green
    ((18, 6, 24), (40, 10, 48), (255, 60, 120), (255, 190, 60)),   # red team
    ((4, 12, 30), (12, 24, 70), (80, 160, 255), (0, 255, 210)),    # blue team
    ((14, 12, 4), (40, 30, 6), (255, 200, 0), (255, 110, 40)),     # warning amber
    ((10, 6, 28), (30, 12, 70), (170, 110, 255), (60, 230, 255)),  # purple team
]


@functools.lru_cache(maxsize=64)
def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


HEAD = "Anton-Regular.ttf"
BODY = "Poppins-Bold.ttf"
MONO = "DejaVuSansMono-Bold.ttf"


def wrap(text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if fnt.getlength(test) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_font(text, name, max_w, max_h, start, min_size=40, spacing=1.08):
    size = start
    while size > min_size:
        f = font(name, size)
        lines = wrap(text, f, max_w)
        if len(lines) * size * spacing <= max_h and all(f.getlength(l) <= max_w for l in lines):
            return f, lines
        size -= 6
    f = font(name, min_size)
    return f, wrap(text, f, max_w)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def back_out(x):
    x = min(max(x, 0.0), 1.0)
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


@functools.lru_cache(maxsize=512)
def text_img(text, name, size, color, stroke=0, stroke_color=(0, 0, 0)):
    f = font(name, size)
    l, t, r, b = f.getbbox(text, stroke_width=stroke)
    img = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - l, 2 - t), text, font=f, fill=color,
                             stroke_width=stroke, stroke_fill=stroke_color)
    return img


def paste_center(canvas, img, cx, cy, scale=1.0, alpha=1.0):
    if scale != 1.0:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                         Image.BILINEAR)
    if alpha < 1.0:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda a: int(a * alpha)))
    canvas.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


class Renderer:
    def __init__(self, script, channel, width=W):
        """width: canvas width the scene layouts use. Shorts use 1080; long-form draws the same
        scenes on a wider virtual canvas and scales them into its 16:9 frame."""
        self.s = script
        self.ch = channel
        self.W = width
        seed = int(hashlib.md5(script["id"].encode()).hexdigest(), 16)
        self.rng = random.Random(seed)
        pals = [tuple(tuple(c) for c in p) for p in channel.get("palettes", [])] or PALETTES
        self.pal = pals[script.get("palette", seed % len(pals))]
        glyphs = channel.get("glyphs", "01{}<>#$/\\:;")
        self.bg_base = self._gradient()
        self.grid = self._grid()
        self.blobs = [(self.rng.random(), self.rng.random(), self.rng.uniform(0.15, 0.35),
                       self.rng.uniform(0.05, 0.12), self.rng.random() * 6.28) for _ in range(4)]
        self.particles = [(self.rng.random() * W, self.rng.random() * H, self.rng.uniform(10, 40),
                           self.rng.choice(glyphs)) for _ in range(28)]

    # ---------- background ----------
    def _gradient(self):
        a, b = np.array(self.pal[0], float), np.array(self.pal[1], float)
        t = np.linspace(0, 1, H)[:, None]
        g = (a * (1 - t) + b * t).astype(np.uint8)
        return Image.fromarray(np.repeat(g[:, None, :], W, axis=1).reshape(H, W, 3)).convert("RGBA")

    def _grid(self):
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        step = self.rng.choice([60, 72, 90])
        col = (*self.pal[2], 14)
        for x in range(0, W, step):
            d.line([(x, 0), (x, H)], fill=col, width=1)
        for y in range(0, H, step):
            d.line([(0, y), (W, y)], fill=col, width=1)
        return img

    def background(self, t):
        small = Image.new("RGBA", (135, 240), (0, 0, 0, 0))
        d = ImageDraw.Draw(small)
        for i, (x, y, r, sp, ph) in enumerate(self.blobs):
            cx = (x + 0.12 * math.sin(t * sp * 6 + ph)) * 135
            cy = (y + 0.10 * math.cos(t * sp * 5 + ph)) * 240
            rr = r * 135
            col = self.pal[2] if i % 2 == 0 else self.pal[3]
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(*col, 70))
        glow = small.filter(ImageFilter.GaussianBlur(18)).resize((W, H), Image.BILINEAR)
        frame = self.bg_base.copy()
        frame.alpha_composite(glow)
        frame.alpha_composite(self.grid)
        d = ImageDraw.Draw(frame)
        f = font(MONO, 26)
        for (x, y, sp, ch) in self.particles:
            yy = (y - t * sp) % H
            d.text((x, yy), ch, font=f, fill=(*self.pal[2], 40))
        return frame

    # ---------- chrome ----------
    def chrome(self, frame, t, total):
        d = ImageDraw.Draw(frame)
        d.rounded_rectangle([60, 70, W - 60, 82], 6, fill=(255, 255, 255, 40))
        d.rounded_rectangle([60, 70, 60 + (W - 120) * min(t / total, 1), 82], 6, fill=self.pal[2])
        tag = text_img(self.ch["name"].upper(), BODY, 34, (*self.pal[2], 255))
        frame.alpha_composite(tag, (60, 110))
        ep = self.s.get("series_tag")
        if ep:
            e = text_img(ep, BODY, 34, (255, 255, 255, 160))
            frame.alpha_composite(e, (W - 60 - e.width, 110))

    # ---------- scene visuals ----------
    def panel(self, frame, x0, y0, x1, y1, alpha=1.0):
        layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle([x0, y0, x1, y1], 28, fill=(0, 0, 0, int(150 * alpha)),
                            outline=(*self.pal[2], int(160 * alpha)), width=3)
        frame.alpha_composite(layer)

    def scene_title(self, frame, sc, p, dur):
        k = back_out(p * dur / 0.45)
        f, lines = fit_font(sc["big"].upper(), HEAD, self.W - 140, 700, 190)
        lh = f.size * 1.08
        y = 760 - len(lines) * lh / 2
        for i, line in enumerate(lines):
            col = self.pal[2] if i == len(lines) - 1 else (255, 255, 255)
            img = text_img(line, HEAD, f.size, (*col, 255), 6)
            paste_center(frame, img, self.W / 2, y + lh * (i + 0.5), 0.6 + 0.4 * k, min(1, k * 1.5))
        if sc.get("sub"):
            a = ease_out((p * dur - 0.35) / 0.4)
            sf, sl = fit_font(sc["sub"], BODY, self.W - 200, 180, 52)
            for i, line in enumerate(sl):
                paste_center(frame, text_img(line, BODY, sf.size, (230, 230, 230, 255), 3),
                             self.W / 2, y + lh * len(lines) + 50 + i * sf.size * 1.2 + 30 * (1 - a),
                             1.0, a)

    def scene_big(self, frame, sc, p, dur):
        k = back_out(p * dur / 0.4)
        self.panel(frame, 80, 340, self.W - 80, 1180, ease_out(p * dur / 0.3))
        f, lines = fit_font(sc["big"], HEAD, self.W - 260, 470, 260)
        lh = f.size * 1.05
        y = 700 - len(lines) * lh / 2
        for i, line in enumerate(lines):
            img = text_img(line, HEAD, f.size, (*self.pal[2], 255), 4)
            paste_center(frame, img, self.W / 2, y + lh * (i + 0.5), 0.5 + 0.5 * k, min(1, k * 1.5))
        if sc.get("sub"):
            a = ease_out((p * dur - 0.3) / 0.4)
            sf, sl = fit_font(sc["sub"], BODY, self.W - 280, 220, 56)
            for i, line in enumerate(sl):
                paste_center(frame, text_img(line, BODY, sf.size, (255, 255, 255, 255)),
                             self.W / 2, 1000 + i * sf.size * 1.2 + 20 * (1 - a), 1.0, a)

    def scene_terminal(self, frame, sc, p, dur):
        x0, y0, x1, y1 = 70, 330, self.W - 70, 1180
        a = ease_out(p * dur / 0.25)
        self.panel(frame, x0, y0 + 40 * (1 - a), x1, y1 + 40 * (1 - a), a)
        d = ImageDraw.Draw(frame)
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([x0 + 34 + i * 44, y0 + 30, x0 + 62 + i * 44, y0 + 58], fill=c)
        f = font(MONO, 44)
        maxc = int((x1 - x0 - 80) / f.getlength("M"))
        rows = []
        for line in sc["lines"]:
            while len(line) > maxc:
                rows.append(line[:maxc])
                line = "  " + line[maxc:]
            rows.append(line)
        total = sum(len(r) for r in rows)
        shown = int(total * min(1, p / 0.75))
        y = y0 + 100
        cursor = (x0 + 40, y)
        for r in rows:
            n = min(len(r), shown)
            shown -= n
            col = self.pal[2] if r.startswith("$") else (225, 225, 225)
            d.text((x0 + 40, y), r[:n], font=f, fill=col)
            if n < len(r):
                cursor = (x0 + 44 + f.getlength(r[:n]), y)
                break
            y += 62
            cursor = (x0 + 40, y)
        if p < 0.75 or int(p * dur * 2.5) % 2 == 0:
            cx, cy = cursor
            d.rectangle([cx, cy + 6, cx + 24, cy + 52], fill=self.pal[2])

    def scene_steps(self, frame, sc, p, dur):
        steps = sc["steps"]
        n = len(steps)
        box_h = min(150, int(800 / n) - 30)
        gap = 30
        top = 760 - (n * box_h + (n - 1) * gap) / 2
        d = ImageDraw.Draw(frame)
        for i, s in enumerate(steps):
            appear = i / n * 0.8
            a = ease_out((p - appear) * dur / 0.35)
            if a <= 0:
                continue
            y = top + i * (box_h + gap)
            dx = 80 * (1 - a)
            layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            ld.rounded_rectangle([100 + dx, y, self.W - 100 + dx, y + box_h], 24,
                                 fill=(0, 0, 0, int(160 * a)), outline=(*self.pal[2], int(220 * a)),
                                 width=3)
            ld.ellipse([130 + dx, y + box_h / 2 - 40, 210 + dx, y + box_h / 2 + 40],
                       fill=(*self.pal[2], int(255 * a)))
            frame.alpha_composite(layer)
            paste_center(frame, text_img(str(i + 1), HEAD, 56, (0, 0, 0, 255)),
                         170 + dx, y + box_h / 2, 1, a)
            sf, sl = fit_font(s, BODY, self.W - 400, box_h - 20, 54, 30)
            for j, line in enumerate(sl):
                img = text_img(line, BODY, sf.size, (255, 255, 255, 255))
                yy = y + box_h / 2 + (j - (len(sl) - 1) / 2) * sf.size * 1.15
                frame.alpha_composite(_fade(img, a), (int(240 + dx), int(yy - img.height / 2)))
            if i < n - 1 and a > 0.9:
                d.polygon([(self.W / 2 - 16, y + box_h + 6), (self.W / 2 + 16, y + box_h + 6),
                           (self.W / 2, y + box_h + gap - 4)], fill=self.pal[3])

    def scene_versus(self, frame, sc, p, dur):
        cols = [(sc["left"], 80, (255, 90, 90)), (sc["right"], self.W / 2 + 10, self.pal[2])]
        cw = self.W / 2 - 90
        content = 0
        for side, _, _ in cols:
            h = 0
            for it in side["items"]:
                sf, sl = fit_font(it, BODY, cw - 60, 200, 42, 28)
                h += len(sl) * sf.size * 1.2 + 26
            content = max(content, h)
        box_h = max(420, 170 + content + 30)
        top = 760 - box_h / 2
        for ci, (side, x, col) in enumerate(cols):
            a = ease_out((p * dur - ci * 0.25) / 0.35)
            if a <= 0:
                continue
            y0 = top + 50 * (1 - a)
            layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rounded_rectangle([x, y0, x + cw, y0 + box_h], 26,
                                                     fill=(0, 0, 0, int(150 * a)),
                                                     outline=(*col, int(220 * a)), width=4)
            frame.alpha_composite(layer)
            paste_center(frame, text_img(side["label"].upper(), HEAD, 80, (*col, 255)),
                         x + cw / 2, y0 + 80, 1, a)
            y = y0 + 170
            items = side["items"]
            for ii, it in enumerate(items):
                ia = ease_out((p - 0.15 - (ci * len(items) + ii) / (2 * len(items)) * 0.6) * dur / 0.3)
                if ia <= 0:
                    break
                sf, sl = fit_font(it, BODY, cw - 60, 200, 42, 28)
                for line in sl:
                    img = text_img(line, BODY, sf.size, (255, 255, 255, 255))
                    frame.alpha_composite(_fade(img, ia), (int(x + 30), int(y)))
                    y += sf.size * 1.2
                y += 26

    def scene_bars(self, frame, sc, p, dur):
        x0, y0, x1, y1 = 80, 340, self.W - 80, 1180
        a0 = ease_out(p * dur / 0.3)
        self.panel(frame, x0, y0 + 30 * (1 - a0), x1, y1 + 30 * (1 - a0), a0)
        top = y0 + 60
        if sc.get("title"):
            tf, tl = fit_font(sc["title"].upper(), HEAD, x1 - x0 - 120, 110, 84, 44)
            paste_center(frame, text_img(tl[0], HEAD, tf.size, (255, 255, 255, 255), 3),
                         self.W / 2, y0 + 75 + 20 * (1 - a0), 1, a0)
            top = y0 + 150
        bars = sc["bars"]
        n = len(bars)
        unit = sc.get("unit", "")
        vmax = max(b["value"] for b in bars) or 1
        decs = [len(str(b["value"]).split(".")[1]) if isinstance(b["value"], float) else 0
                for b in bars]

        def fmt(v, dp):
            return (f"{v:,.{dp}f}" if dp else f"{int(round(v)):,}") + unit

        bx0, bx1 = x0 + 60, x1 - 60
        region = (y1 - 50) - top
        row_h = min(200, region / n)
        ls = int(min(50, row_h * 0.32))
        bar_h = int(min(64, row_h * 0.38))
        start = top + (region - row_h * n) / 2
        # one shared value size so every number fits beside the longest label
        lab_w = max(font(BODY, ls).getlength(b["label"]) for b in bars)
        vs = int(ls * 1.25)
        while vs > 30 and lab_w + 30 + max(font(HEAD, vs).getlength(fmt(b["value"], d))
                                          for b, d in zip(bars, decs)) > bx1 - bx0:
            vs -= 2
        for i, (b, dp) in enumerate(zip(bars, decs)):
            appear = 0.08 + i / n * 0.6
            a = ease_out((p - appear) * dur / 0.3)
            if a <= 0:
                continue
            g = ease_out((p - appear) * dur / 0.9)
            ry = start + i * row_h + (row_h - ls * 1.3 - 12 - bar_h) / 2 + 20 * (1 - a)
            frame.alpha_composite(_fade(text_img(b["label"], BODY, ls, (235, 235, 235, 255)), a),
                                  (int(bx0), int(ry)))
            val = text_img(fmt(b["value"] * g, dp), HEAD, vs, (*self.pal[2], 255))
            frame.alpha_composite(_fade(val, a), (int(bx1 - val.width),
                                                  int(ry + ls * 1.3 - val.height + 4)))
            by = ry + ls * 1.3 + 12
            col = self.pal[2] if b["value"] == vmax else self.pal[3]
            layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            ld.rounded_rectangle([bx0, by, bx1, by + bar_h], bar_h // 2,
                                 fill=(255, 255, 255, int(28 * a)))
            bw = (bx1 - bx0) * b["value"] / vmax * g
            if bw >= 2:
                ld.rounded_rectangle([bx0, by, bx0 + max(bw, bar_h), by + bar_h], bar_h // 2,
                                     fill=(*col, int(255 * a)))
            frame.alpha_composite(layer)

    def scene_quiz(self, frame, sc, p, dur):
        x0, x1 = 80, self.W - 80
        a0 = ease_out(p * dur / 0.3)
        qf, ql = fit_font(sc["question"], BODY, x1 - x0 - 100, 200, 62, 36, 1.2)
        qlh = qf.size * 1.2
        opts = sc["options"]
        n = len(opts)
        gap = 26
        q_h = 100 + len(ql) * qlh + 50
        box_h = min(140, ((1180 - 340 - q_h - 44) - (n - 1) * gap) / n)
        # centre question card + options in the content area
        y0 = 340 + max(0, (1180 - 340 - (q_h + 44 + n * box_h + (n - 1) * gap)) / 2)
        qy1 = y0 + q_h
        self.panel(frame, x0, y0 + 30 * (1 - a0), x1, qy1 + 30 * (1 - a0), a0)
        lab = text_img("QUIZ", HEAD, 44, (*self.pal[2], 255))
        frame.alpha_composite(_fade(lab, a0), (x0 + 40, int(y0 + 30 + 30 * (1 - a0))))
        for i, line in enumerate(ql):
            paste_center(frame, text_img(line, BODY, qf.size, (255, 255, 255, 255)),
                         self.W / 2, y0 + 100 + qlh * (i + 0.5) + 30 * (1 - a0), 1, a0)
        reveal = 0.6
        # countdown strip under the question until the reveal
        if 0.4 < p < reveal + 0.05:
            cd = 1 - min(max((p - 0.4) / (reveal - 0.4), 0), 1)
            d = ImageDraw.Draw(frame)
            d.rounded_rectangle([x0 + 40, qy1 - 26, x0 + 40 + (x1 - x0 - 80) * cd, qy1 - 16], 5,
                                fill=self.pal[3])
        oy0 = qy1 + 44
        cr = min(40, box_h / 2 - 14)
        tx_off = 30 + 2 * cr + 30
        tw = (self.W - 200) - 130 - tx_off
        # one shared text size so options look consistent
        osz = min(fit_font(o, BODY, tw, box_h - 24, 50, 30, 1.15)[0].size for o in opts)
        r = (p - reveal) * dur
        ra = ease_out(r / 0.3) if r > 0 else 0
        for i, opt in enumerate(opts):
            appear = 0.12 + i / n * 0.3
            a = ease_out((p - appear) * dur / 0.35)
            if a <= 0:
                continue
            right = i == sc["answer"]
            dim = 1 - 0.65 * ra if not right else 1
            aa = a * dim
            y = oy0 + i * (box_h + gap)
            dx = 80 * (1 - a)
            bx0, bx1 = 100 + dx, self.W - 100 + dx
            cy = y + box_h / 2
            layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            if right and ra > 0:
                fill = tuple(int(c * ra) for c in self.pal[2]) + (int(160 + 90 * ra),)
            else:
                fill = (0, 0, 0, int(160 * aa))
            ld.rounded_rectangle([bx0, y, bx1, y + box_h], 24, fill=fill,
                                 outline=(*self.pal[2], int(220 * aa)), width=3)
            badge = (0, 0, 0, int(255 * aa)) if right and ra > 0.5 else (*self.pal[2], int(255 * aa))
            ld.ellipse([bx0 + 30, cy - cr, bx0 + 30 + 2 * cr, cy + cr], fill=badge)
            frame.alpha_composite(layer)
            letter_col = (*self.pal[2], 255) if right and ra > 0.5 else (0, 0, 0, 255)
            paste_center(frame, text_img("ABCD"[i], HEAD, int(cr * 1.3), letter_col),
                         bx0 + 30 + cr, cy, 1, aa)
            tx = bx0 + tx_off
            sf = font(BODY, osz)
            sl = wrap(opt, sf, tw)
            tcol = (0, 0, 0, 255) if right and ra > 0.5 else (255, 255, 255, 255)
            for j, line in enumerate(sl):
                img = text_img(line, BODY, sf.size, tcol)
                yy = cy + (j - (len(sl) - 1) / 2) * sf.size * 1.15
                frame.alpha_composite(_fade(img, aa), (int(tx), int(yy - img.height / 2)))
            if right and r > 0:
                self._tick(frame, bx1 - 70, cy, min(46, box_h / 2 - 10), r)

    def _tick(self, frame, cx, cy, rad, r):
        """Animated tick in a circle, drawn with lines (no emoji glyphs)."""
        s = back_out(r / 0.3)
        rr = rad * s
        layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(0, 0, 0, 235))
        pts = [(cx - rad * 0.48, cy + rad * 0.02), (cx - rad * 0.12, cy + rad * 0.38),
               (cx + rad * 0.52, cy - rad * 0.36)]
        k = min(max((r - 0.1) / 0.35, 0), 1)
        lw = max(4, int(rad * 0.2))
        if k > 0:
            seg1 = min(k / 0.4, 1)
            end1 = (pts[0][0] + (pts[1][0] - pts[0][0]) * seg1,
                    pts[0][1] + (pts[1][1] - pts[0][1]) * seg1)
            line = [pts[0], end1]
            if k > 0.4:
                seg2 = (k - 0.4) / 0.6
                line.append((pts[1][0] + (pts[2][0] - pts[1][0]) * seg2,
                             pts[1][1] + (pts[2][1] - pts[1][1]) * seg2))
            ld.line(line, fill=(*self.pal[2], 255), width=lw, joint="curve")
            for q in (line[0], line[-1]):
                ld.ellipse([q[0] - lw / 2, q[1] - lw / 2, q[0] + lw / 2, q[1] + lw / 2],
                           fill=(*self.pal[2], 255))
        frame.alpha_composite(layer)

    def scene_timeline(self, frame, sc, p, dur):
        x0, y0, x1, y1 = 80, 340, self.W - 80, 1180
        a0 = ease_out(p * dur / 0.3)
        self.panel(frame, x0, y0 + 30 * (1 - a0), x1, y1 + 30 * (1 - a0), a0)
        ev = sc["events"]
        n = len(ev)
        lx = x0 + 110
        pad = 70
        step = (y1 - y0 - 2 * pad) / n
        ys = [y0 + pad + step * (i + 0.5) for i in range(n)]
        ysz = int(min(84, step * 0.44))
        tx = lx + 70
        tw = x1 - 50 - tx
        appears = [0.06 + i / n * 0.7 for i in range(n)]
        # shared text size so every event reads the same
        tsz = min(fit_font(e["text"], BODY, tw, step - ysz * 1.15 - 18, 54, 28, 1.15)[0].size
                  for e in ev)
        # line grows from the first dot to the latest revealed one
        line_end = ys[0]
        for i in range(1, n):
            g = ease_out((p - appears[i] + 0.06) * dur / 0.35)
            if g <= 0:
                break
            line_end = ys[i - 1] + (ys[i] - ys[i - 1]) * g
        track = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        ImageDraw.Draw(track).line([(lx, ys[0] - step * 0.4), (lx, ys[-1] + step * 0.4)],
                                   fill=(255, 255, 255, int(40 * a0)), width=6)
        frame.alpha_composite(track)
        d = ImageDraw.Draw(frame)
        if p * dur > 0.15:
            d.line([(lx, ys[0] - step * 0.4 * a0), (lx, line_end)], fill=self.pal[2], width=8)
        for i, e in enumerate(ev):
            a = ease_out((p - appears[i]) * dur / 0.35)
            if a <= 0:
                continue
            k = back_out((p - appears[i]) * dur / 0.35)
            cy = ys[i]
            layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            rr = 24 * k
            ld.ellipse([lx - rr - 8, cy - rr - 8, lx + rr + 8, cy + rr + 8],
                       fill=(*self.pal[2], int(60 * a)))
            ld.ellipse([lx - rr, cy - rr, lx + rr, cy + rr], fill=(*self.pal[2], int(255 * a)),
                       outline=(0, 0, 0, int(255 * a)), width=4)
            frame.alpha_composite(layer)
            tf = font(BODY, tsz)
            tl = wrap(e["text"], tf, tw)
            block = ysz * 1.08 + len(tl) * tf.size * 1.15
            top = cy - block / 2
            dx = 60 * (1 - a)
            yimg = text_img(e["year"], HEAD, ysz, (*self.pal[2], 255))
            frame.alpha_composite(_fade(yimg, a), (int(tx + dx), int(top)))
            for j, line in enumerate(tl):
                img = text_img(line, BODY, tf.size, (255, 255, 255, 255))
                frame.alpha_composite(_fade(img, a),
                                      (int(tx + dx), int(top + ysz * 1.08 + j * tf.size * 1.15)))

    # ---------- captions ----------
    def caption_groups(self, words, max_words=4, max_chars=22):
        key = (id(words), len(words), max_words, max_chars)
        if getattr(self, "_groups_key", None) != key:
            groups, cur = [], []
            for w in words:
                cur.append(w)
                if len(cur) >= max_words or w["word"][-1:] in ".,!?;:" or \
                        len(" ".join(x["word"] for x in cur)) > max_chars:
                    groups.append(cur)
                    cur = []
            if cur:
                groups.append(cur)
            self._groups_key, self._groups = key, groups
        return self._groups

    def captions(self, frame, words, t, y=1270, size=74, max_w=None, max_words=4, max_chars=22,
                 min_size=44):
        """Word-highlighted captions centred on the frame (Shorts defaults; long-form passes its own)."""
        fw = frame.width
        max_w = fw - 280 if max_w is None else max_w
        groups = self.caption_groups(words, max_words, max_chars)
        g = next((g for g in groups if g[0]["start"] - 0.05 <= t <= g[-1]["end"] + 0.25), None)
        if not g:
            return
        f = font(BODY, size)
        texts = [w["word"].upper() for w in g]
        space = f.getlength(" ")
        widths = [f.getlength(x) for x in texts]
        while sum(widths) + space * (len(texts) - 1) > max_w and size > min_size:
            size -= 4
            f = font(BODY, size)
            space = f.getlength(" ")
            widths = [f.getlength(x) for x in texts]
        x = (fw - (sum(widths) + space * (len(texts) - 1))) / 2
        pop = back_out((t - g[0]["start"]) / 0.18)
        for w, txt, wd in zip(g, texts, widths):
            active = w["start"] <= t <= w["end"] + 0.05
            if active:
                layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                ImageDraw.Draw(layer).rounded_rectangle(
                    [x - 14, y - 10, x + wd + 14, y + size * 1.25], 16, fill=(*self.pal[2], 235))
                frame.alpha_composite(layer)
            col = (0, 0, 0, 255) if active else (255, 255, 255, 255)
            img = text_img(txt, BODY, size, col, 0 if active else 5)
            paste_center(frame, img, x + wd / 2, y + size * 0.6, 0.85 + 0.15 * pop)
            x += wd + space

    # ---------- main ----------
    def build_audio(self, workdir, mode, lead=None):
        """lead: optional {scene_index: seconds} of extra silence before a scene (long-form
        chapter cards)."""
        lead = lead or {}
        scenes = self.s["scenes"]
        timeline, words_all, wavs = [], [], []
        t = 0.0
        for i, sc in enumerate(scenes):
            mp3 = os.path.join(workdir, f"s{i}.mp3")
            words, dur = tts.synth_scene(sc["say"], self.ch["voice"], self.ch.get("rate", "+8%"),
                                         mp3, mode)
            wav = os.path.join(workdir, f"s{i}.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100",
                            "-ac", "1", wav], check=True)
            wavs.append(wav)
            t += lead.get(i, 0)
            for w in words:
                words_all.append({**w, "start": w["start"] + t, "end": w["end"] + t})
            timeline.append((t, dur))
            t += dur + GAP
        total = t + 0.6
        # stitch with gaps + a soft whoosh at each cut (synthesised, no licensed audio)
        sr = 44100
        out = np.zeros(int(total * sr) + sr, np.float32)
        rng = np.random.default_rng(7)
        for (st, dur), wav in zip(timeline, wavs):
            with wave.open(wav) as wf:
                data = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
            a = int(st * sr)
            out[a:a + len(data)] += data
            if st > 0:
                n = int(0.35 * sr)
                noise = rng.standard_normal(n).astype(np.float32)
                noise = np.convolve(noise, np.ones(40) / 40, mode="same")
                env = np.sin(np.linspace(0, math.pi, n)) ** 2
                b = max(0, a - int(0.2 * sr))
                out[b:b + n] += noise * env * 0.35
        out = np.clip(out, -1, 1)
        path = os.path.join(workdir, "voice.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes((out * 32767).astype(np.int16).tobytes())
        return path, timeline, words_all, total

    def render(self, out_path, workdir, mode="edge"):
        os.makedirs(workdir, exist_ok=True)
        audio, timeline, words, total = self.build_audio(workdir, mode)
        proc = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_path],
            stdin=subprocess.PIPE)
        for fi in range(int(total * FPS)):
            frame = self.frame_at(fi / FPS, timeline, words, total)
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        return total

    def scene_index(self, t, timeline):
        idx = 0
        for i, (st, _) in enumerate(timeline):
            if t >= st - 0.08:
                idx = i
        return idx

    def draw_scene(self, frame, idx, t, timeline):
        """Draw scene idx's visual (no background, chrome or captions) onto frame."""
        draw = {"title": self.scene_title, "big": self.scene_big, "terminal": self.scene_terminal,
                "steps": self.scene_steps, "versus": self.scene_versus, "bars": self.scene_bars,
                "quiz": self.scene_quiz, "timeline": self.scene_timeline}
        st, dur = timeline[idx]
        span = dur + GAP
        p = min(max((t - st) / span, 0), 1)
        sc = self.s["scenes"][idx]
        draw[sc.get("kind", "big")](frame, sc, p, span)

    def frame_at(self, t, timeline, words, total):
        """One portrait Short frame (RGBA) at time t."""
        idx = self.scene_index(t, timeline)
        frame = self.background(t)
        self.chrome(frame, t, total)
        self.draw_scene(frame, idx, t, timeline)
        self.captions(frame, words, t)
        return frame


def _fade(img, a):
    if a >= 1:
        return img
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return img


def main():
    """python -m shorts.render <script.json> <out.mp4> [edge|silent]
    The channel is the folder two levels above the script (channels/<slug>/queue/x.json)."""
    script_path, out = sys.argv[1], sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "edge"
    ch_dir = os.path.dirname(os.path.dirname(os.path.abspath(script_path)))
    with open(os.path.join(ch_dir, "channel.json")) as f:
        channel = json.load(f)
    with open(script_path) as f:
        script = json.load(f)
    dur = Renderer(script, channel).render(out, out + ".work", mode)
    print(f"rendered {out} ({dur:.1f}s)")


if __name__ == "__main__":
    main()
