"""Channel-styled stills for long-form videos: thumbnails (1280x720) and chapter cards.

Uses the same visual language and fonts as branding/make_branding.py:
  cyber  - green-bar printout, key word knocked out of a redaction bar  (Anonymous Pro)
  gaming - pixel sky + brick wall with a glowing secret brick           (Unifont, hard pixels)
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
def _gaming(w, h, kicker, text, highlight):
    gw, gh = 160, 90
    u = max(1, w // gw)
    art = Image.new("RGB", (gw, gh), mb.SKY)
    d = ImageDraw.Draw(art)
    for y in range(0, 12):
        for x in range((y // 2) % 2, gw, 2):
            if y % 2 == 0:
                d.point((x, y), fill=mb.SKY2)
    import math
    hill = [(0, 70)] + [(x, 64 + int(4 * math.sin(x / 9)) + int(2 * math.sin(x / 3.3)))
                        for x in range(0, gw + 1, 2)] + [(gw, gh), (0, gh)]
    d.polygon(hill, fill=mb.HILL)
    for y in range(78, gh):
        d.line([(0, y), (gw, y)], fill=mb.BRICK if y > 78 else mb.BRICK_HI)
    for x in range(0, gw, 6):
        d.rectangle([x, 80, x + 4, 82], fill=mb.MORTAR)
    wx0 = gw - 32
    art.paste(mb.brick_wall(24, 51, hole=(8, 17, 16, 27), seed=len(text)), (wx0, 28))
    for (px, py) in [(wx0 - 3, 77), (wx0 - 6, 77), (wx0 - 4, 76)]:
        d.rectangle([px, py, px + 1, py], fill=mb.BRICK_HI)
    img = art.resize((gw * u, gh * u), Image.NEAREST).convert("RGBA")
    x0 = 6 * u
    max_w = (wx0 - 6) * u - x0
    ks = max(2, u // 2)
    img.alpha_composite(mb.pixel_text(kicker, ks, mb.GLOW, mb.NAVY), (x0, 5 * u))
    # Unifont is 8px per character at 16px: choose the biggest whole-number scale that fits
    words = text.split()
    best = None
    for scale in range(16, 2, -1):
        lines = _wrap(words, lambda s: len(s) * 8 * scale, max_w)
        if len(lines) <= 3 and all(len(" ".join(l)) * 8 * scale <= max_w for l in lines) \
                and len(lines) * 18 * scale * 1.05 <= 56 * u:
            best = scale, lines
            break
    scale, lines = best or (3, _wrap(words, lambda s: len(s) * 24, max_w))
    lh = int(18 * scale * 1.05)
    top = 14 * u + (56 * u - len(lines) * lh) // 2
    for i, line in enumerate(lines):
        x = x0
        for word in line:
            col = mb.GLOW if highlight and _clean(word) == highlight else mb.WHITE
            t = mb.pixel_text(word, scale, col, mb.NAVY)
            img.alpha_composite(t, (x, top + i * lh))
            x += (len(word) + 1) * 8 * scale
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
