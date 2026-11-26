"""Channel art: 800x800 profile pictures and 2560x1440 banners.

Each channel borrows its look from its own subject instead of a shared template:
  cyber  - green-bar printer paper with redaction bars        (Anonymous Pro)
  gaming - a sealed boss arena: arched boss door, torches, a boss health bar (Unifont bitmap type)
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


# Boss Room Archive v2: a sealed boss arena, catalogued. (v1 brick wall read too much like Mario.)
STONE, STONE_HI, STONE_LO, MORT2 = (44, 30, 35), (62, 44, 49), (33, 22, 26), (18, 12, 14)
TORCH, TORCH_HI, BOSSRED, BOSSRED_HI, BOSSRED_LO = (242, 163, 58), (255, 226, 140), (200, 32, 46), (240, 86, 86), (86, 14, 22)
GOLD2, GOLD2_LO, BONE, WOOD, WOOD_HI, IRON = (217, 164, 65), (140, 98, 34), (230, 220, 203), (70, 28, 30), (98, 42, 42), (58, 56, 62)


def stone_wall(gw, gh, seed=1, block=(10, 6)):
    """Large ashlar blocks with 1px mortar, top-lit, randomly chipped."""
    rng = random.Random(seed)
    bw, bh = block
    img = Image.new("RGB", (gw, gh), MORT2)
    d = ImageDraw.Draw(img)
    for r, y in enumerate(range(0, gh, bh)):
        off = 0 if r % 2 == 0 else bw // 2
        for x in range(-off, gw, bw):
            shade = rng.choice([STONE, STONE, STONE_LO])
            d.rectangle([x, y, x + bw - 2, y + bh - 2], fill=shade)
            d.line([(x, y), (x + bw - 2, y)], fill=STONE_HI)
            for _ in range(rng.randint(0, 2)):
                d.point((x + rng.randint(1, bw - 3), y + rng.randint(1, bh - 3)), fill=MORT2)
    return img


def light(img, cx, cy, radius, colour, strength=0.55):
    """Warm pixel-stepped light pool (banded, not a smooth gradient)."""
    px = img.load()
    for y in range(max(0, cy - radius), min(img.height, cy + radius)):
        for x in range(max(0, cx - radius), min(img.width, cx + radius)):
            dd = math.hypot(x - cx, (y - cy) * 1.2) / radius
            if dd < 1:
                k = strength * (round((1 - dd) * 4) / 4)  # 4 hard bands
                r, g, b = px[x, y]
                px[x, y] = tuple(int(c + (t - c) * k * 0.5) for c, t in zip((r, g, b), colour))


def torch(d, x, y, frame=0):
    d.rectangle([x - 1, y, x + 1, y + 9], fill=IRON)
    d.rectangle([x - 2, y, x + 2, y + 1], fill=GOLD2_LO)
    flame = [(0, -1, 2), (-1, -2, 2), (0, -3, 1), (1, -4, 1), (0, -5, 0)]
    for dx, dy, w in flame:
        d.line([(x + dx - w, y + dy), (x + dx + w, y + dy)], fill=TORCH)
    d.point((x, y - 2), fill=TORCH_HI)
    d.point((x, y - 1), fill=TORCH_HI)


def boss_door(d, cx, top, w, h):
    """Arched double door with iron bands and red light under it."""
    x0, x1, y1 = cx - w // 2, cx + w // 2, top + h
    arch = w // 2
    d.rectangle([x0 - 2, top + arch - 2, x1 + 2, y1], fill=MORT2)
    d.ellipse([x0 - 2, top - 2, x1 + 2, top + 2 * arch + 2], fill=MORT2)
    d.ellipse([x0, top, x1, top + 2 * arch], fill=WOOD)
    d.rectangle([x0, top + arch, x1, y1 - 1], fill=WOOD)
    for x in range(x0 + 2, x1, 3):  # planks, clipped to the arch
        yt = top + arch - math.sqrt(max(arch ** 2 - (x - cx) ** 2, 0)) + 2
        d.line([(x, int(yt)), (x, y1 - 1)], fill=WOOD_HI)
    d.line([(cx, top + 1), (cx, y1 - 1)], fill=MORT2)
    for by in (top + arch + 2, y1 - 5):  # iron bands + rivets
        d.line([(x0, by), (x1, by)], fill=IRON)
        for x in range(x0 + 1, x1, 4):
            d.point((x, by), fill=GOLD2)
    d.rectangle([cx - 2, top + arch + 5, cx - 1, top + arch + 7], fill=GOLD2)  # handles
    d.rectangle([cx + 1, top + arch + 5, cx + 2, top + arch + 7], fill=GOLD2)
    d.line([(x0, y1), (x1, y1)], fill=BOSSRED_HI)  # light leaking under the door
    for i, c in enumerate((BOSSRED, BOSSRED_LO)):
        d.line([(x0 + i * 2, y1 + 1 + i), (x1 - i * 2, y1 + 1 + i)], fill=c)


def health_bar(d, x0, y, w, fill_frac=0.72):
    """Boss health bar: gold frame, red fill with a highlight row, chipped-off damage segment."""
    d.rectangle([x0 - 2, y - 2, x0 + w + 1, y + 6], fill=MORT2)
    d.rectangle([x0 - 1, y - 1, x0 + w, y + 5], outline=GOLD2)
    d.rectangle([x0, y, x0 + w - 1, y + 4], fill=BOSSRED_LO)
    fw = int(w * fill_frac)
    d.rectangle([x0, y, x0 + fw, y + 4], fill=BOSSRED)
    d.line([(x0, y), (x0 + fw, y)], fill=BOSSRED_HI)
    d.rectangle([x0 + fw + 1, y, x0 + fw + 10, y + 4], fill=TORCH)  # recent damage, catching up
    for x in range(x0 + w // 4, x0 + w, w // 4):  # phase ticks
        d.line([(x, y - 2), (x, y - 1)], fill=GOLD2)


BAYER = [[0, 2], [3, 1]]


def dither_light(img, cx, cy, radius, colour, mix=0.28, squash=0.8):
    """Pixel-art light: solid / checker / sparse dither rings that tint stone but not mortar."""
    px = img.load()
    for y in range(max(0, cy - radius), min(img.height, cy + radius + 1)):
        for x in range(max(0, cx - radius), min(img.width, cx + radius + 1)):
            if px[x, y] == MORT2:
                continue
            dd = math.hypot(x - cx, (y - cy) * squash) / radius
            level = 4 if dd < 0.4 else 2 if dd < 1 else 0  # solid core, checker edge
            if level and BAYER[y % 2][x % 2] < level:
                r, g, b = px[x, y]
                px[x, y] = tuple(int(c + (t - c) * mix) for c, t in zip((r, g, b), colour))


def arch_ring(d, cx, cy, r_in, r_out, n=9):
    """Voussoir stones around an arch (top half circle), mortar lines between stones."""
    for yy in range(cy - r_out, cy + 1):
        for xx in range(cx - r_out, cx + r_out + 1):
            dist = math.hypot(xx - cx, yy - cy)
            if r_in < dist <= r_out:
                ang = math.atan2(cy - yy, xx - cx)  # 0..pi
                seam = abs((ang / math.pi * n) % 1 - 0.5) > 0.42
                edge = dist > r_out - 1
                d.point((xx, yy), fill=MORT2 if seam else STONE_HI if edge else STONE)


def pixel_label(art, text, x, y, fill, outline):
    """Unifont drawn at the art's own pixel size, with a 1px outline and drop shadow."""
    t = pixel_text(text, 1, fill)
    sil = Image.new("RGBA", t.size, (*outline, 255))
    sil.putalpha(t.getchannel("A"))
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (2, 2), (1, 2), (2, 1)]:
        art.alpha_composite(sil, (x + dx, y + dy))
    art.alpha_composite(t, (x, y))


def gaming_banner():
    u = 8
    gw, gh = BW // u, BH // u  # 320 x 180; everything is drawn on this one grid
    rng = random.Random(11)
    art = Image.new("RGB", (gw, gh), MORT2)
    d = ImageDraw.Draw(art)
    # back wall: hand-varied block widths per course, not one repeating tile
    y = 0
    while y < 140:
        bh = rng.choice([7, 8, 8, 9])
        x = -rng.randint(0, 12)
        while x < gw:
            bw = rng.choice([12, 14, 16, 18, 22])
            c = rng.choice([STONE, STONE, STONE, STONE_LO])
            d.rectangle([x, y, x + bw - 2, y + bh - 2], fill=c)
            d.line([(x, y), (x + bw - 2, y)], fill=STONE_HI)
            d.line([(x + bw - 2, y + 1), (x + bw - 2, y + bh - 2)], fill=STONE_LO)
            x += bw
        y += bh
    for _ in range(9):  # cracks
        cx, cy = rng.randint(0, gw), rng.randint(5, 130)
        for i in range(rng.randint(4, 9)):
            d.point((cx, cy), fill=MORT2)
            cx += rng.choice([-1, 0, 1]); cy += 1
    # floor, side-on like a 2D game: slab line, uneven slabs, rubble
    fy = 121
    d.rectangle([0, fy, gw, gh], fill=STONE_LO)
    d.line([(0, fy), (gw, fy)], fill=STONE_HI)
    x = 0
    while x < gw:
        d.line([(x, fy + 1), (x, fy + 8)], fill=MORT2)
        x += rng.randint(14, 30)
    d.rectangle([0, fy + 9, gw, gh], fill=MORT2)
    for _ in range(18):
        rx = rng.randint(0, gw)
        d.rectangle([rx, fy - 1, rx + rng.randint(0, 2), fy - 1], fill=STONE_HI)
    # the boss door, right of the title, in a voussoir arch
    cx, w = SX1 // u - 24, 28
    top = fy - 4 - 50
    arch_ring(d, cx, top + w // 2, w // 2 + 1, w // 2 + 6, n=7)
    for side in (-1, 1):
        x0 = cx - w // 2 - 6 if side < 0 else cx + w // 2
        d.rectangle([x0, top + w // 2, x0 + 6, fy - 1], fill=STONE)
        d.line([(x0 + (6 if side < 0 else 0), top + w // 2), (x0 + (6 if side < 0 else 0), fy - 1)], fill=STONE_LO)
        for yy in range(top + w // 2 + 6, fy, 7):
            d.line([(x0, yy), (x0 + 6, yy)], fill=MORT2)
    boss_door(d, cx, top, w, fy - 4 - top)
    for i in range(0, 40, 3):  # one chain, off-centre
        d.rectangle([SX0 // u + 30, i, SX0 // u + 31, i + 1], outline=IRON)
    torches = [(SX0 // u - 10, 84), (cx + 30, 80)]
    for tx, ty in torches:
        dither_light(art, tx, ty - 4, 18, TORCH, 0.22)
    dither_light(art, cx, fy, 22, BOSSRED, 0.35, squash=2.2)  # flat spill along the floor
    d = ImageDraw.Draw(art)
    for tx, ty in torches:
        torch(d, tx, ty)
    # boss intro: name over a health bar, on the same grid as the art
    art = art.convert("RGBA")
    bar_x = SX0 // u + 4
    pixel_label(art, "Boss Room Archive", bar_x, 72, BONE, MORT2)
    health_bar(ImageDraw.Draw(art), bar_x, 92, 136)
    return art.resize((BW, BH), Image.NEAREST).convert("RGB")


def gaming_pfp():
    g = 40
    art = stone_wall(g, g, seed=3, block=(9, 5))
    d = ImageDraw.Draw(art)
    d.rectangle([0, 34, g, g], fill=MORT2)
    d.line([(0, 34), (g, 34)], fill=STONE_HI)
    dither_light(art, 20, 35, 18, BOSSRED, 0.35, squash=2.5)
    d = ImageDraw.Draw(art)
    arch_ring(d, 20, 19, 10, 14, n=7)
    boss_door(d, 20, 9, 20, 22)
    return art.resize((800, 800), Image.NEAREST)


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
