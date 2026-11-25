"""Channel art: 800x800 profile pictures and 2560x1440 banners.

Each channel borrows its look from its own subject instead of a shared template:
  cyber  - green-bar printer paper with redaction bars        (Anonymous Pro)
  gaming - a pixel brick wall with one brick knocked out       (Unifont, real bitmap type)
  tech   - a purple PCB with gold pads and white silkscreen    (TeX Gyre Heros Condensed)

Banner safe area (visible on every device): 1546x423, centred.
Usage: python branding/make_branding.py  -> branding/out/<slug>_pfp.png, <slug>_banner.png
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
FONT = lambda name, size: ImageFont.truetype(os.path.join(HERE, "fonts", name), size)
BW, BH = 2560, 1440
SX0, SY0, SX1, SY1 = (BW - 1546) // 2, (BH - 423) // 2, (BW + 1546) // 2, (BH + 423) // 2


def rough_bar(d, x0, y0, x1, y1, rng, fill=(0, 0, 0)):
    """A marker-drawn redaction bar: straight-ish, slightly uneven edges."""
    pts, steps = [], max(6, int((x1 - x0) / 40))
    for i in range(steps + 1):
        pts.append((x0 + (x1 - x0) * i / steps, y0 + rng.uniform(-3, 3)))
    for i in range(steps, -1, -1):
        pts.append((x0 + (x1 - x0) * i / steps, y1 + rng.uniform(-3, 3)))
    d.polygon(pts, fill=fill)


# ======================= Plain Text Threats: printout =======================
PAPER, BAR, EDGE, INK = (243, 246, 241), (213, 232, 212), (195, 204, 194), (32, 38, 58)


def greenbar(w, h, band, offset=0, feed=True):
    img = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(img)
    y = offset - band * 2 * (offset // (band * 2) + 1)
    while y < h:
        d.rectangle([0, y, w, y + band - 1], fill=BAR)
        y += band * 2
    if feed:  # tractor-feed strips with sprocket holes and perforation
        for x0 in (0, w - 130):
            d.rectangle([x0, 0, x0 + 130, h], fill=PAPER)
            for yy in range(band // 2, h, band):
                cx = x0 + 65
                d.ellipse([cx - 22, yy - 22, cx + 22, yy + 22], fill=EDGE)
        for x in (130, w - 130):
            for yy in range(0, h, 18):
                d.line([(x, yy), (x, yy + 9)], fill=EDGE, width=3)
    return img


def cyber_banner():
    rng = random.Random(3)
    img = greenbar(BW, BH, 72, offset=SY0 - 6)
    d = ImageDraw.Draw(img)
    x = SX0 + 20
    size = 172
    while FONT("AnonymousPro-Bold.ttf", size).getlength("Plain Text Threats") > 1546 - 60:
        size -= 4
    title = FONT("AnonymousPro-Bold.ttf", size)
    d.text((x, SY0 + 10), "Plain Text Threats", font=title, fill=INK)
    body = FONT("AnonymousPro-Regular.ttf", 54)
    y = SY0 + 228
    pre, hidden, post = "How ", "attacks", " actually work, and how to stop them."
    d.text((x, y), pre, font=body, fill=INK)
    hx = x + body.getlength(pre)
    hw = body.getlength(hidden)
    rough_bar(d, hx - 4, y + 8, hx + hw + 4, y + 60, rng)
    d.text((hx + hw, y), post, font=body, fill=INK)
    d.text((x, y + 92), "New Short every hour.", font=FONT("AnonymousPro-Bold.ttf", 54), fill=INK)
    return img


def cyber_pfp():
    rng = random.Random(5)
    s = 800
    img = greenbar(s, s, 112, offset=150, feed=False)
    d = ImageDraw.Draw(img)
    f = FONT("AnonymousPro-Bold.ttf", 180)
    bw = f.getlength("plain")
    x = (s - bw) / 2
    d.text((x, 150), "plain", font=f, fill=INK)
    d.text((x, 340), "text", font=f, fill=INK)
    rough_bar(d, x - 4, 570, x + bw + 4, 650, rng)
    return img


# ======================= Boss Room Archive: pixel wall =======================
SKY, SKY2, HILL = (35, 64, 184), (28, 52, 156), (24, 40, 118)
BRICK, BRICK_HI, MORTAR = (140, 59, 46), (169, 80, 63), (58, 31, 26)
GLOW, GLOW2, NAVY, WHITE = (255, 210, 63), (255, 236, 150), (20, 33, 61), (255, 255, 255)


def pixel_text(text, scale, colour, shadow=None):
    f = FONT("unifont.otf", 16)
    w = int(f.getlength(text)) + 2
    small = Image.new("RGBA", (w, 18), (0, 0, 0, 0))
    sd = ImageDraw.Draw(small)
    if shadow:
        sd.text((1, 1), text, font=f, fill=shadow)
    sd.text((0, 0), text, font=f, fill=colour)
    a = small.getchannel("A").point(lambda v: 255 if v > 110 else 0)  # hard pixels
    small.putalpha(a)
    return small.resize((w * scale, 18 * scale), Image.NEAREST)


def brick_wall(gw, gh, hole=None, seed=1):
    """gw x gh pixel image of bricks (4x2 cells, 1px mortar). hole = (x0,y0,x1,y1) in pixels."""
    rng = random.Random(seed)
    img = Image.new("RGB", (gw, gh), MORTAR)
    d = ImageDraw.Draw(img)
    for row in range(0, gh, 3):
        off = 0 if (row // 3) % 2 == 0 else 2
        for col in range(-off, gw, 5):
            d.rectangle([col, row, col + 3, row + 1], fill=BRICK)
            d.line([(col, row), (col + 3, row)], fill=BRICK_HI)
            if rng.random() < 0.12:
                d.point((col + rng.randint(0, 3), row + 1), fill=MORTAR)
    if hole:
        x0, y0, x1, y1 = hole
        d.rectangle([x0, y0, x1, y1], fill=GLOW)
        d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], fill=GLOW2)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        for dy, (a, b) in {-3: (-1, 0), -2: (-2, 1), -1: (-2, 1), 0: (-1, 0), 1: (-1, 0),
                           2: (-1, 0), 3: (-2, 1)}.items():
            d.line([(cx + a, cy + dy), (cx + b, cy + dy)], fill=NAVY)
        for y in range(y0, y1 + 1):  # broken, jagged edges
            if rng.random() < 0.5:
                d.point((x0 - 1, y), fill=MORTAR)
            if rng.random() < 0.5:
                d.point((x1 + 1, y), fill=MORTAR)
    return img


def gaming_banner():
    u = 16
    gw, gh = BW // u, BH // u  # 160 x 90
    art = Image.new("RGB", (gw, gh), SKY)
    d = ImageDraw.Draw(art)
    for y in range(0, 18):
        for x in range((y // 2) % 2, gw, 2):
            if y % 2 == 0:
                d.point((x, y), fill=SKY2)
    hill = [(0, 70)] + [(x, 62 + int(4 * math.sin(x / 9)) + int(2 * math.sin(x / 3.3))) for x in range(0, gw + 1, 2)] + [(gw, gh), (0, gh)]
    d.polygon(hill, fill=HILL)
    for y in range(76, gh):
        d.line([(0, y), (gw, y)], fill=BRICK if y > 76 else BRICK_HI)
    for x in range(0, gw, 6):
        d.rectangle([x, 78, x + 4, 80], fill=MORTAR)
    wx0 = SX1 // u - 24
    art.paste(brick_wall(24, 50, hole=(8, 17, 16, 27), seed=4), (wx0, 27))
    for (px, py) in [(wx0 - 3, 75), (wx0 - 6, 75), (wx0 - 4, 74)]:
        d.rectangle([px, py, px + 1, py], fill=BRICK_HI)
    img = art.resize((BW, BH), Image.NEAREST).convert("RGBA")
    x = SX0 + 24
    img.alpha_composite(pixel_text("Boss Room Archive", 6, WHITE, NAVY), (x, SY0 + 50))
    img.alpha_composite(pixel_text("The secrets games never put in the manual.", 3, WHITE), (x + 6, SY0 + 205))
    img.alpha_composite(pixel_text("New secret every day.", 3, GLOW), (x + 6, SY0 + 275))
    return img.convert("RGB")


def gaming_pfp():
    return brick_wall(32, 32, hole=(12, 11, 20, 20), seed=2).resize((800, 800), Image.NEAREST)


# ======================= Pocket Silicon: purple PCB =======================
MASK, COPPER, GOLD, SILK, DRILL = (62, 31, 110), (88, 52, 140), (217, 169, 68), (244, 244, 242), (26, 15, 46)


def via(d, x, y, r=14):
    d.ellipse([x - r, y - r, x + r, y + r], fill=GOLD)
    d.ellipse([x - r * 0.45, y - r * 0.45, x + r * 0.45, y + r * 0.45], fill=DRILL)


def trace(d, pts, w=12):
    d.line(pts, fill=COPPER, width=w, joint="curve")


def chip(d, cx, cy, size, pins, label=None, label_font=None, pad=(16, 42)):
    h = size / 2
    pitch = size / (pins + 1)
    ends = []
    pw, pl = pad
    for i in range(1, pins + 1):
        o = -h + i * pitch
        for (px, py, horiz, ox, oy) in [(cx + o, cy - h, False, 0, -1), (cx + o, cy + h, False, 0, 1),
                                        (cx - h, cy + o, True, -1, 0), (cx + h, cy + o, True, 1, 0)]:
            if horiz:
                d.rectangle([px - pl / 2, py - pw / 2, px + pl / 2, py + pw / 2], fill=GOLD)
            else:
                d.rectangle([px - pw / 2, py - pl / 2, px + pw / 2, py + pl / 2], fill=GOLD)
            ends.append((px + ox * pl / 2, py + oy * pl / 2, ox, oy))
    m = h - pl / 2 - 18
    d.rectangle([cx - m, cy - m, cx + m, cy + m], outline=SILK, width=5)
    d.ellipse([cx - m + 18, cy - m + 18, cx - m + 36, cy - m + 36], fill=SILK)  # pin-1 mark
    if label:
        l, t, r, b = d.textbbox((0, 0), label, font=label_font)
        d.text((cx - (r - l) / 2 - l, cy - (b - t) / 2 - t + 8), label, font=label_font, fill=SILK)
    return ends


def fan_out(d, ends, cx, cy, reach, w, first=40, slope=0.5):
    """Route each pad straight out, then at 45 degrees away from centre."""
    for (x, y, ox, oy) in ends:
        if oy:
            k = x - cx
            pts = [(x, y), (x, y + oy * first), (x + k * slope, y + oy * (first + abs(k) * slope)),
                   (x + k * slope, y + oy * reach)]
        else:
            k = y - cy
            pts = [(x, y), (x + ox * first, y), (x + ox * (first + abs(k) * slope), y + k * slope),
                   (x + ox * reach, y + k * slope)]
        trace(d, pts, w)
        yield pts[-1], (ox, oy)


def tech_banner():
    img = Image.new("RGB", (BW, BH), MASK)
    d = ImageDraw.Draw(img)
    cx, cy, size = SX1 - 230, (SY0 + SY1) // 2, 300
    ends = chip(ImageDraw.Draw(Image.new("RGB", (1, 1))), cx, cy, size, 5)
    for (end, (ox, oy)) in fan_out(d, ends, cx, cy, 900, 12, first=50, slope=0.9):
        if ox == -1:  # left-going traces stop at vias before reaching the title
            pass
    # re-route left side shorter, ending in vias clear of the text
    for (x, y, ox, oy) in ends:
        if ox == -1:
            k = y - cy
            end = (x - 70 - abs(k) * 0.9 - 40, y + k * 0.9)
            d.rectangle([end[0] - 20, end[1] - 30, x - 1, end[1] + 30], fill=MASK) if False else None
    for (mx, my) in [(110, 110), (BW - 110, 110), (110, BH - 110), (BW - 110, BH - 110)]:
        d.ellipse([mx - 46, my - 46, mx + 46, my + 46], fill=GOLD)
        d.ellipse([mx - 30, my - 30, mx + 30, my + 30], fill=DRILL)
    for i, y in enumerate([330, 362, 394]):  # a bus above the title
        trace(d, [(170 + i * 32, y), (SX0 + 700 - i * 32, y), (SX0 + 760 - i * 32, y + 60), (SX0 + 1060, y + 60)], 10)
        via(d, 170 + i * 32, y, 12)
        via(d, SX0 + 1060, y + 60, 12)
    for i, y in enumerate([1046, 1078, 1110]):  # and one below
        trace(d, [(BW - 170 - i * 32, y), (SX0 + 500 + i * 32, y), (SX0 + 440 + i * 32, y - 60), (SX0 + 160, y - 60)], 10)
        via(d, BW - 170 - i * 32, y, 12)
        via(d, SX0 + 160, y - 60, 12)
    # clear a quiet field for the title, then draw the chip on top
    d.rectangle([SX0 - 10, SY0 - 20, cx - size / 2 - 120, SY1 + 10], fill=MASK)
    chip(d, cx, cy, size, 5, "U1", FONT("texgyreheroscn-bold.otf", 64))
    x = SX0 + 20
    d.text((x, SY0 - 4), "Pocket Silicon", font=FONT("texgyreheroscn-bold.otf", 200), fill=SILK)
    body = FONT("texgyreheroscn-regular.otf", 58)
    d.text((x + 6, SY0 + 236), "How AI and everyday tech actually work,", font=body, fill=SILK)
    d.text((x + 6, SY0 + 304), "explained simply. New explainer every day.", font=body, fill=SILK)
    d.text((SX1 - 120, SY1 + 20), "rev 1.0", font=FONT("texgyreheroscn-regular.otf", 34), fill=SILK)
    return img


def tech_pfp():
    s = 800
    img = Image.new("RGB", (s, s), MASK)
    d = ImageDraw.Draw(img)
    cx = cy = s // 2
    ends = chip(ImageDraw.Draw(Image.new("RGB", (1, 1))), cx, cy, 380, 4, pad=(22, 54))
    for _ in fan_out(d, ends, cx, cy, 300, 14):
        pass
    chip(d, cx, cy, 380, 4, "PC", FONT("texgyreheroscn-bold.otf", 150), pad=(22, 54))
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for slug, (pf, bn) in {"cyber": (cyber_pfp, cyber_banner), "gaming": (gaming_pfp, gaming_banner),
                           "tech": (tech_pfp, tech_banner)}.items():
        pf().save(os.path.join(OUT, f"{slug}_pfp.png"))
        b = bn()
        b.save(os.path.join(OUT, f"{slug}_banner.png"))
        b.save(os.path.join(OUT, f"{slug}_banner.jpg"), quality=90)
    print("ok")
