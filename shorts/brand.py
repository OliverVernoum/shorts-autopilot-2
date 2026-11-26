"""Channel-styled stills for long-form videos: thumbnails (1280x720) and chapter cards.

Uses the same visual language and fonts as branding/make_branding.py:
  cyber  - green-bar printout, key word knocked out of a redaction bar  (Anonymous Pro)
  gaming - stone boss arena, torch, sealed boss door, boss health bar    (Unifont, hard pixels)
  tech   - purple PCB, gold pads, white silkscreen, key word in gold    (TeX Gyre Heros Cn)
Any other channel gets a flat card in its first palette.

  card(slug, w, h, kicker, text, highlight=None, channel=None) -> RGB image
  thumbnail(script, channel, slug, path) -> path of the saved PNG
"""
import importlib.util
import os
import random
import re

from PIL import Image, ImageDraw

from . import render

_spec = importlib.util.spec_from_file_location(
    "make_branding", os.path.join(render.ROOT, "branding", "make_branding.py"))
mb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mb)

DW, DH = 2560, 1440  # design canvas for the vector styles (same as the banners), scaled down after
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "it", "is", "how", "why",
        "what", "your", "you", "that", "this", "with", "get", "gets", "actually", "really"}


def _clean(w):
    return re.sub(r"[^\w'-]", "", w).lower()


def _wrap(words, measure, max_w):
    lines, cur = [], []
    for w in words:
        if cur and measure(" ".join(cur + [w])) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _fit(words, font_fn, max_w, max_h, start, stop, step, lh=1.08, max_lines=3):
    """Largest size whose wrapped lines fit; prefers fewer, bigger lines."""
    size = start
    while size > stop:
        f = font_fn(size)
        lines = _wrap(words, f.getlength, max_w)
        if len(lines) <= max_lines and len(lines) * size * lh <= max_h and \
                all(f.getlength(" ".join(l)) <= max_w for l in lines):
            return f, lines
        size -= step
    f = font_fn(stop)
    return f, _wrap(words, f.getlength, max_w)


# ------------------------------------------------------------------ cyber
def _cyber(w, h, kicker, text, highlight):
    rng = random.Random(text)
    img = mb.greenbar(DW, DH, 72, offset=40)
    d = ImageDraw.Draw(img)
    x0, x1 = 230, DW - 230
    kf = mb.FONT("AnonymousPro-Bold.ttf", 64)
    d.text((x0, 106), kicker, font=kf, fill=mb.INK)
    d.line([(x0, 196), (x0 + kf.getlength(kicker), 196)], fill=mb.INK, width=5)
    words = text.split()
    f, lines = _fit(words, lambda s: mb.FONT("AnonymousPro-Bold.ttf", s), x1 - x0, 860, 330, 90, 6,
                    lh=1.16)
    size = f.size
    lh = size * 1.16
    top = 250 + (900 - len(lines) * lh) / 2
    space = f.getlength(" ")
    for i, line in enumerate(lines):
        x, y = x0, top + i * lh
        for word in line:
            ww = f.getlength(word)
            if highlight and _clean(word) == highlight:
                l, t, r, b = f.getbbox(word)
                mb.rough_bar(d, x - 14, y + t - 16, x + ww + 14, y + b + 18, rng, fill=mb.INK)
                d.text((x, y), word, font=f, fill=mb.PAPER)
            else:
                d.text((x, y), word, font=f, fill=mb.INK)
            x += ww + space
    # a redacted "paragraph" running off the bottom of the page
    y = DH - 170
    x = x0
    while x1 - x > 160:
        bw = min(rng.randint(140, 420), x1 - x)
        mb.rough_bar(d, x, y, x + bw, y + 46, rng, fill=mb.INK)
        x += bw + rng.randint(30, 60)
    return img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------ gaming
def _px_word(word, col, scale):
    """Unifont word with a 1px outline + drop shadow, drawn on its own grid then scaled whole."""
    t = mb.pixel_text(word, 1, col)
    out = Image.new("RGBA", (t.width + 3, t.height + 3), (0, 0, 0, 0))
    sil = Image.new("RGBA", t.size, (*mb.MORT2, 255))
    sil.putalpha(t.getchannel("A"))
    for dx, dy in [(0, 1), (2, 1), (1, 0), (1, 2), (2, 2), (3, 3), (2, 3), (3, 2)]:
        out.alpha_composite(sil, (dx, dy))
    out.alpha_composite(t, (1, 1))
    return out.resize((out.width * scale, out.height * scale), Image.NEAREST)


def _gaming(w, h, kicker, text, highlight):
    """Boss Room Archive: stone arena, torch, sealed boss door, boss health bar under the title."""
    gw, gh = 160, 90
    u = max(1, w // gw)
    art = mb.stone_wall(gw, gh, seed=len(text), block=(12, 7))
    d = ImageDraw.Draw(art)
    fy = 76
    d.rectangle([0, fy, gw, gh], fill=mb.STONE_LO)
    d.line([(0, fy), (gw, fy)], fill=mb.STONE_HI)
    d.rectangle([0, fy + 6, gw, gh], fill=mb.MORT2)
    cx, dw = gw - 20, 22
    top = fy - 4 - 40
    mb.arch_ring(d, cx, top + dw // 2, dw // 2 + 1, dw // 2 + 5, n=7)
    for x0 in (cx - dw // 2 - 5, cx + dw // 2):
        d.rectangle([x0, top + dw // 2, x0 + 5, fy - 1], fill=mb.STONE)
    tx = cx - dw // 2 - 12
    mb.dither_light(art, tx, 40, 16, mb.TORCH, 0.22)
    mb.dither_light(art, cx, fy, 16, mb.BOSSRED, 0.35, squash=2.2)
    d = ImageDraw.Draw(art)
    mb.boss_door(d, cx, top, dw, fy - 4 - top)
    mb.torch(d, tx, 44)
    img = art.resize((gw * u, gh * u), Image.NEAREST).convert("RGBA")
    x0 = 6 * u
    max_w = (tx - 8) * u - x0
    img.alpha_composite(_px_word(kicker, mb.TORCH, max(1, u // 2)), (x0, 5 * u))
    # biggest whole-number Unifont scale that fits: the grid's own pixel size first, then half
    words = text.split()
    best = None
    for scale in range(u, max(1, u // 3) - 1, -1):
        lines = _wrap(words, lambda s: len(s) * 8 * scale, max_w)
        if len(lines) <= 3 and all(len(" ".join(l)) * 8 * scale <= max_w for l in lines) \
                and len(lines) * 17 * scale <= 51 * u:
            best = scale, lines
            break
    scale, lines = best or (max(1, u // 3), _wrap(words, lambda s: len(s) * 8 * max(1, u // 3), max_w))
    lh = 17 * scale
    top_y = 13 * u + (51 * u - len(lines) * lh) // 2
    for i, line in enumerate(lines):
        x = x0
        for word in line:
            col = mb.TORCH if highlight and _clean(word) == highlight else mb.BONE
            img.alpha_composite(_px_word(word, col, scale), (x, top_y + i * lh))
            x += (len(word) + 1) * 8 * scale
    bar = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    mb.health_bar(ImageDraw.Draw(bar), 6, min(fy - 9, (top_y + len(lines) * lh) // u + 3),
                  (tx - 14) - 6, fill_frac=0.3 + (len(text) % 5) / 10)
    img.alpha_composite(bar.resize((gw * u, gh * u), Image.NEAREST))
    out = img.convert("RGB")
    return out if out.size == (w, h) else out.resize((w, h), Image.NEAREST)


# ------------------------------------------------------------------ tech
def _tech(w, h, kicker, text, highlight):
    img = Image.new("RGB", (DW, DH), mb.MASK)
    d = ImageDraw.Draw(img)
    cx, cy, size = DW - 400, DH // 2 + 40, 360
    ends = mb.chip(ImageDraw.Draw(Image.new("RGB", (1, 1))), cx, cy, size, 5)
    text_x1 = cx - size / 2 - 150
    for _ in mb.fan_out(d, [e for e in ends if e[2] != -1], cx, cy, 1400, 12, first=50, slope=0.9):
        pass
    left = [e for e in ends if e[2] == -1]
    for (end, _) in mb.fan_out(d, left, cx, cy, left[0][0] - text_x1 - 20, 12, first=40, slope=0.5):
        mb.via(d, end[0], end[1], 16)
    for i, y in enumerate([150, 182, 214]):  # a bus along the top, ending in vias
        mb.trace(d, [(330 + i * 32, y), (1300 - i * 32, y), (1360 - i * 32, y + 60),
                     (text_x1 - 40, y + 60)], 10)
        mb.via(d, 330 + i * 32, y, 12)
        mb.via(d, text_x1 - 40, y + 60, 12)
    for (mx, my) in [(110, 110), (DW - 110, 110), (110, DH - 110), (DW - 110, DH - 110)]:
        d.ellipse([mx - 46, my - 46, mx + 46, my + 46], fill=mb.GOLD)
        d.ellipse([mx - 30, my - 30, mx + 30, my + 30], fill=mb.DRILL)
    mb.chip(d, cx, cy, size, 5, "U1", mb.FONT("texgyreheroscn-bold.otf", 72))
    x0 = 200
    kf = mb.FONT("texgyreheroscn-bold.otf", 72)
    l, t, r, b = d.textbbox((0, 0), kicker, font=kf)
    d.rectangle([x0 - 26, 300, x0 + (r - l) + 26, 300 + (b - t) + 52], outline=mb.SILK, width=5)
    d.text((x0 - l, 326 - t), kicker, font=kf, fill=mb.SILK)
    words = text.upper().split()
    f, lines = _fit(words, lambda s: mb.FONT("texgyreheroscn-bold.otf", s), text_x1 - x0 - 60,
                    860, 420, 100, 8, lh=1.0)
    lh = f.size * 1.0
    top = 450 + (900 - len(lines) * lh) / 2 - f.size * 0.12
    space = f.getlength(" ")
    for i, line in enumerate(lines):
        x = x0
        for word in line:
            col = mb.GOLD if highlight and _clean(word) == highlight else mb.SILK
            d.text((x, top + i * lh), word, font=f, fill=col)
            x += f.getlength(word) + space
    d.text((DW - 330, DH - 200), "rev 1.0", font=mb.FONT("texgyreheroscn-regular.otf", 40),
           fill=mb.SILK)
    return img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------ fallback
def _plain(w, h, kicker, text, highlight, channel):
    pal = [tuple(c) for c in (channel or {}).get("palettes", [render.PALETTES[0]])[0]]
    img = Image.new("RGB", (DW, DH), pal[0])
    d = ImageDraw.Draw(img)
    d.rectangle([0, DH - 60, DW, DH], fill=pal[2])
    x0 = 200
    d.text((x0, 140), kicker, font=render.font(render.BODY, 70), fill=pal[2])
    f, lines = _fit(text.upper().split(), lambda s: render.font(render.HEAD, s), DW - 2 * x0, 1000,
                    400, 100, 8)
    top = 280 + (1000 - len(lines) * f.size * 1.08) / 2
    for i, line in enumerate(lines):
        x = x0
        for word in line:
            col = pal[2] if highlight and _clean(word) == highlight else (255, 255, 255)
            d.text((x, top + i * f.size * 1.08), word, font=f, fill=col)
            x += f.getlength(word + " ")
    return img.resize((w, h), Image.LANCZOS)


def card(slug, w, h, kicker, text, highlight=None, channel=None):
    hl = _clean(highlight) if highlight else None
    if slug == "cyber":
        return _cyber(w, h, kicker, text, hl)
    if slug == "gaming":
        return _gaming(w, h, kicker, text, hl)
    if slug == "tech":
        return _tech(w, h, kicker, text, hl)
    return _plain(w, h, kicker, text, hl, channel)


def thumb_words(script):
    """(text, highlight): thumb_text/thumb_highlight, else 3-6 words derived from the title."""
    text = script.get("thumb_text")
    if not text:
        head = re.split(r"\s[—–:|-]\s|:\s|\?\s", script["title"])[0]
        if len(head.split()) < 3:
            head = script["title"]
        words = [w for w in head.split() if w][:6]
        while len(words) > 3 and _clean(words[-1]) in STOP | {"behind", "about", "from", "into"}:
            words.pop()  # don't end a cut-down title on a dangling little word
        text = " ".join(words)
    hl = script.get("thumb_highlight")
    if not hl:
        cands = [w for w in text.split() if _clean(w) not in STOP] or text.split()
        hl = max(cands, key=lambda w: len(_clean(w)))
    return text, _clean(hl)


def thumbnail(script, channel, slug, path):
    text, hl = thumb_words(script)
    img = card(slug, 1280, 720, channel.get("name", slug), text, hl, channel)
    img.save(path, optimize=True)
    if os.path.getsize(path) > 2_000_000:  # YouTube's custom thumbnail limit is 2 MB
        path = os.path.splitext(path)[0] + ".jpg"
        img.save(path, quality=92)
    return path
