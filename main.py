#!/usr/bin/env python3
"""
VELMARA — a travel poster for a place that isn't there.

Draws one vintage screen-print style travel poster for the invented
twin-sunset isle of Velmara and writes it to /output/entry.png.

Pure Python standard library: the rasteriser, the lettering and the
PNG encoder are all hand-rolled here. No network, no third-party code.

Method
------
* The scene is painted at 2x supersampling with flat span fills
  (rects, circles, scanline polygons, capsule strokes for the type).
* It is then box-downsampled and quantised onto a fixed screen-print
  palette with Bayer ordered dithering, which doubles as the print
  grain, and written as an indexed PNG.
"""

import math
import random
import struct
import zlib

OUT_PATH = "/output/entry.png"

W, H = 768, 1024          # final poster size (portrait)
SS = 2                    # supersampling factor
SW, SH = W * SS, H * SS   # working buffer size

# ---------------------------------------------------------------- palette
# Screen-print palette: a handful of flat inks. Each ink gets shade
# variants so the ordered dither has neighbours to step between.

PAPER = (244, 234, 213)   # warm cream paper
INK = (17, 40, 49)        # deep teal-navy ink
SKY = [
    (16, 54, 66),         # top: deep dusk teal
    (22, 80, 88),
    (38, 112, 106),
    (74, 144, 114),
    (128, 164, 108),
    (186, 174, 100),
    (226, 158, 88),       # peach
    (240, 186, 108),      # horizon glow
]
SUN_CORE = (250, 216, 128)
SUN_EDGE = (244, 182, 94)
FAR_MTN = (46, 102, 102)
ISLAND = (18, 47, 58)
SEA = (21, 80, 90)
SEA_LIGHT = (70, 136, 128)
REFL = (240, 190, 100)
GOLD = (242, 192, 99)
CORAL = (198, 96, 64)
LIGHTHOUSE = (240, 230, 205)
BEAM = (250, 226, 150)


def _shade(rgb, f):
    return tuple(max(0, min(255, int(round(c * f)))) for c in rgb)


def build_palette():
    bases = [PAPER, INK, SUN_CORE, SUN_EDGE, FAR_MTN, ISLAND, SEA,
             SEA_LIGHT, REFL, GOLD, CORAL, LIGHTHOUSE, BEAM] + SKY
    pal, seen = [], set()
    for base in bases:
        for f in (0.88, 0.94, 1.0, 1.06, 1.12):
            c = _shade(base, f)
            if c not in seen:
                seen.add(c)
                pal.append(c)
    return pal


PALETTE = build_palette()

# ---------------------------------------------------------------- buffer
buf = [bytearray(SW * 3) for _ in range(SH)]
CLIP = (0, 0, SW, SH)     # current clip rect, supersampled coords


def set_clip(x0, y0, x1, y1):
    global CLIP
    CLIP = (int(x0 * SS), int(y0 * SS), int(x1 * SS), int(y1 * SS))


def span(y, x0, x1, rgb):
    """Fill a horizontal run on supersampled row y."""
    cx0, _, cx1, _ = CLIP
    if y < CLIP[1] or y >= CLIP[3]:
        return
    x0 = max(int(x0), cx0)
    x1 = min(int(x1), cx1)
    if x1 <= x0:
        return
    row = buf[y]
    row[x0 * 3:x1 * 3] = bytes(rgb) * (x1 - x0)


def fill_rect(x, y, w, h, rgb):
    for yy in range(int(y * SS), int((y + h) * SS)):
        span(yy, x * SS, (x + w) * SS, rgb)


def fill_circle(cx, cy, r, rgb):
    cx, cy, r = cx * SS, cy * SS, r * SS
    ri = int(r)
    for dy in range(-ri, ri + 1):
        half = int(math.isqrt(max(0, ri * ri - dy * dy)))
        span(int(cy) + dy, cx - half, cx + half, rgb)


def fill_poly(pts, rgb):
    """Scanline polygon fill; pts are final-res (x, y) pairs."""
    p = [(x * SS, y * SS) for x, y in pts]
    ys = [q[1] for q in p]
    y0, y1 = int(min(ys)), int(max(ys))
    n = len(p)
    for y in range(y0, y1 + 1):
        yc = y + 0.5
        xs = []
        for i in range(n):
            xa, ya = p[i]
            xb, yb = p[(i + 1) % n]
            if (ya <= yc < yb) or (yb <= yc < ya):
                xs.append(xa + (yc - ya) * (xb - xa) / (yb - ya))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            span(y, xs[i], xs[i + 1], rgb)


def blend_poly(pts, rgb, alpha):
    """Polygon filled with an alpha blend over what is already drawn."""
    p = [(x * SS, y * SS) for x, y in pts]
    ys = [q[1] for q in p]
    y0, y1 = int(min(ys)), int(max(ys))
    n = len(p)
    ia = 1.0 - alpha
    for y in range(y0, y1 + 1):
        if y < CLIP[1] or y >= CLIP[3]:
            continue
        yc = y + 0.5
        xs = []
        for i in range(n):
            xa, ya = p[i]
            xb, yb = p[(i + 1) % n]
            if (ya <= yc < yb) or (yb <= yc < ya):
                xs.append(xa + (yc - ya) * (xb - xa) / (yb - ya))
        xs.sort()
        row = buf[y]
        for i in range(0, len(xs) - 1, 2):
            x0 = max(int(xs[i]), CLIP[0])
            x1 = min(int(xs[i + 1]), CLIP[2])
            for x in range(x0, x1):
                j = x * 3
                row[j] = int(row[j] * ia + rgb[0] * alpha)
                row[j + 1] = int(row[j + 1] * ia + rgb[1] * alpha)
                row[j + 2] = int(row[j + 2] * ia + rgb[2] * alpha)


def capsule(x1, y1, x2, y2, r, rgb):
    """A thick round-ended stroke, in final-res coordinates."""
    x1, y1, x2, y2, r = x1 * SS, y1 * SS, x2 * SS, y2 * SS, r * SS
    bx0 = max(int(min(x1, x2) - r - 1), CLIP[0])
    bx1 = min(int(max(x1, x2) + r + 2), CLIP[2])
    by0 = max(int(min(y1, y2) - r - 1), CLIP[1])
    by1 = min(int(max(y1, y2) + r + 2), CLIP[3])
    dx, dy = x2 - x1, y2 - y1
    len2 = dx * dx + dy * dy
    r2 = r * r
    for y in range(by0, by1):
        row = buf[y]
        py = y + 0.5
        for x in range(bx0, bx1):
            px = x + 0.5
            if len2 == 0:
                d2 = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = ((px - x1) * dx + (py - y1) * dy) / len2
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                d2 = (px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2
            if d2 <= r2:
                j = x * 3
                row[j:j + 3] = bytes(rgb)


def dot(x, y, r, rgb):
    fill_circle(x, y, r, rgb)

# ---------------------------------------------------------------- lettering
# A hand-drawn single-stroke lettering set on a 10 x 14 grid (y down).
# Each glyph is a list of strokes; each stroke is a list of grid points.

GLYPHS = {
    "A": [[(0, 14), (5, 0), (10, 14)], [(2.4, 9.2), (7.6, 9.2)]],
    "C": [[(9.2, 3.2), (6.4, 0.9), (3.4, 0.9), (1.0, 3.2), (0.7, 7),
           (1.0, 10.8), (3.4, 13.1), (6.4, 13.1), (9.2, 10.8)]],
    "E": [[(9, 0), (1, 0), (1, 14), (9, 14)], [(1, 7), (7.4, 7)]],
    "H": [[(1, 0), (1, 14)], [(9, 0), (9, 14)], [(1, 7), (9, 7)]],
    "I": [[(5, 0), (5, 14)], [(1.6, 0), (8.4, 0)], [(1.6, 14), (8.4, 14)]],
    "L": [[(1, 0), (1, 14), (9, 14)]],
    "M": [[(1, 14), (1, 0), (5, 7.6), (9, 0), (9, 14)]],
    "N": [[(1, 14), (1, 0), (9, 14), (9, 0)]],
    "R": [[(1, 14), (1, 0), (6.2, 0), (8.8, 1.6), (8.8, 5.2), (6.2, 7),
           (1, 7)], [(4.6, 7), (9.2, 14)]],
    "S": [[(8.8, 2.6), (6.2, 0.8), (3.4, 1.0), (1.4, 3.0), (2.0, 5.6),
           (4.2, 7.2), (7.2, 8.8), (8.6, 10.8), (7.0, 13.0), (3.6, 13.2),
           (1.0, 11.4)]],
    "T": [[(0, 0), (10, 0)], [(5, 0), (5, 14)]],
    "U": [[(1, 0), (1, 8.8), (2.4, 12.4), (5, 14), (7.6, 12.4), (9, 8.8),
           (9, 0)]],
    "V": [[(0, 0), (5, 14), (10, 0)]],
    "W": [[(0, 0), (2.4, 14), (5, 4.2), (7.6, 14), (10, 0)]],
    "-": [[(2.4, 7), (7.6, 7)]],
}


def text_width(text, cap, tracking):
    unit = cap / 14.0
    adv = 10.0 + tracking
    return sum(adv if ch != " " else adv * 0.9 for ch in text) * unit - tracking * unit


def draw_text(text, cx, top, cap, rgb, tracking=2.6, shadow=None):
    """Centred stroke lettering; cap = cap height in final-res px."""
    unit = cap / 14.0
    adv = 10.0 + tracking
    total = text_width(text, cap, tracking)
    x = cx - total / 2.0
    passes = [(shadow, 5, 6)] if shadow else []
    passes.append((rgb, 0, 0))
    for colour, ox, oy in passes:
        if colour is None:
            continue
        xx = x
        for ch in text:
            if ch == " ":
                xx += adv * 0.9 * unit
                continue
            for stroke in GLYPHS[ch]:
                pts = [(xx + gx * unit + ox, top + gy * unit + oy)
                       for gx, gy in stroke]
                for i in range(len(pts) - 1):
                    capsule(pts[i][0], pts[i][1], pts[i + 1][0],
                            pts[i + 1][1], 1.02 * unit, colour)
            xx += adv * unit

# ---------------------------------------------------------------- the scene
# Scene lives inside a cream frame: paper margin, ink keyline, then the
# printed picture.

FRAME = 30                # paper margin
LINE = 42                 # scene inset
SX0, SY0 = LINE, LINE
SX1, SY1 = W - LINE, H - LINE
SCW, SCH = SX1 - SX0, SY1 - SY0
HORIZON = 560             # scene-local y of the horizon


def scene_poly(pts, rgb):
    fill_poly([(SX0 + x, SY0 + y) for x, y in pts], rgb)


def paint():
    rng = random.Random(20261121)

    # paper everywhere first
    set_clip(0, 0, W, H)
    fill_rect(0, 0, W, H, PAPER)

    set_clip(SX0, SY0, SX1, SY1)

    # --- sky: flat screen-print bands with dithered joins -------------
    band_h = HORIZON / len(SKY)
    for i, col in enumerate(SKY):
        y0 = i * band_h
        fill_rect(SX0, SY0 + y0, SCW, band_h + 1, col)
    for i in range(len(SKY) - 1):
        yb = SY0 + (i + 1) * band_h
        a, b = SKY[i], SKY[i + 1]
        for yy in range(int((yb - 5) * SS), int((yb + 5) * SS)):
            row = buf[yy]
            for xx in range(SX0 * SS, SX1 * SS):
                if (xx // 3 + yy // 3) % 2 == 0:
                    row[xx * 3:xx * 3 + 3] = bytes(b if (yy // 3) % 2 else a)

    # --- early stars in the top band ----------------------------------
    for _ in range(46):
        x = SX0 + rng.uniform(6, SCW - 6)
        y = SY0 + rng.uniform(4, 120)
        dot(x, y, rng.uniform(0.8, 1.7), PAPER if rng.random() < 0.7 else GOLD)

    # --- the great sun, low between the peaks --------------------------
    sun_cx, sun_cy, sun_r = SX0 + SCW / 2, SY0 + 468, 128
    fill_circle(sun_cx, sun_cy, 188, _shade(SUN_EDGE, 1.02))
    fill_circle(sun_cx, sun_cy, 164, _shade(SUN_EDGE, 1.05))
    fill_circle(sun_cx, sun_cy, 144, _shade(SUN_EDGE, 1.09))
    fill_circle(sun_cx, sun_cy, sun_r, SUN_EDGE)
    fill_circle(sun_cx, sun_cy, sun_r - 16, SUN_CORE)

    # --- far range, dipping at the centre ------------------------------
    scene_poly([(0, 560), (0, 452), (90, 418), (170, 452), (250, 500),
                (330, 528), (400, 528), (470, 492), (545, 440), (610, 420),
                (684, 452), (684, 560)], FAR_MTN)

    # --- the sea --------------------------------------------------------
    fill_rect(SX0, SY0 + HORIZON, SCW, SCH - HORIZON, SEA)
    for _ in range(52):  # quiet horizontal sea-light streaks
        y = SY0 + rng.uniform(HORIZON + 26, SCH - 24)
        x = SX0 + rng.uniform(0, SCW - 70)
        fill_rect(x, y, rng.uniform(20, 68), 2.2, SEA_LIGHT)

    # --- the island: twin peaks, a notch for the sun --------------------
    scene_poly([(36, 606), (60, 520), (110, 452), (168, 402), (214, 430),
                (258, 500), (300, 528), (342, 536), (388, 524), (430, 486),
                (472, 424), (516, 398), (560, 428), (606, 500), (640, 556),
                (652, 606)], ISLAND)

    # --- lighthouse on the east peak ------------------------------------
    lx, lbase = SX0 + 516, SY0 + 398
    fill_poly([(lx - 15, lbase), (lx - 10, lbase - 52), (lx + 10, lbase - 52),
               (lx + 15, lbase)], LIGHTHOUSE)
    fill_rect(lx - 12.5, lbase - 36, 25, 8, CORAL)
    fill_rect(lx - 12.5, lbase - 16, 25, 8, CORAL)
    fill_rect(lx - 8, lbase - 64, 16, 12, GOLD)          # lamp room
    fill_poly([(lx - 12, lbase - 64), (lx + 12, lbase - 64),
               (lx, lbase - 78)], INK)                  # roof
    dot(lx, lbase - 58, 4.2, SUN_CORE)
    # its beam, a slim wedge sweeping west over the dusk sky
    blend_poly([(lx - 6, lbase - 58), (SX0 + 150, SY0 + 318),
                (SX0 + 138, SY0 + 344)], BEAM, 0.22)

    # --- the sun's road on the water ------------------------------------
    for i, y in enumerate(range(618, 884, 15)):
        wob = rng.uniform(-7, 7)
        wdt = 40 + i * 2.4 + rng.uniform(-6, 10)
        cx = SX0 + SCW / 2 + wob
        col = REFL if i % 3 else SUN_CORE
        n = 1 if rng.random() < 0.4 else 2
        seg = wdt / n
        for s in range(n):
            fill_rect(cx - wdt / 2 + s * seg + 2, SY0 + y, seg - 5, 4.6, col)

    # --- a small boat, sailing home --------------------------------------
    bx, by = SX0 + 168, SY0 + 706
    fill_poly([(bx - 30, by), (bx + 30, by), (bx + 19, by + 13),
               (bx - 19, by + 13)], INK)
    capsule(bx, by, bx, by - 46, 2.2, INK)
    fill_poly([(bx + 4, by - 44), (bx + 4, by - 4), (bx + 27, by - 4)], PAPER)
    fill_poly([(bx - 4, by - 38), (bx - 4, by - 4), (bx - 21, by - 4)],
              _shade(PAPER, 0.92))
    fill_poly([(bx, by - 52), (bx + 13, by - 46), (bx, by - 40)], CORAL)

    # --- foreground shore: a dark strip with rocks -----------------------
    shore = [(0, SCH), (0, 902), (80, 892), (170, 900), (260, 890),
             (360, 898), (450, 888), (540, 898), (620, 890), (684, 900),
             (684, SCH)]
    scene_poly(shore, INK)
    scene_poly([(52, 902), (92, 874), (134, 902)], INK)
    scene_poly([(556, 898), (600, 870), (644, 898)], INK)

    # --- gulls, kept clear of the lettering --------------------------------
    for gx, gy, s in ((88, 306, 1.0), (136, 336, 0.7), (592, 300, 0.85)):
        x, y = SX0 + gx, SY0 + gy
        capsule(x - 11 * s, y, x, y - 5 * s, 1.7, INK)
        capsule(x, y - 5 * s, x + 11 * s, y, 1.7, INK)

    # --- the name and the promise -----------------------------------------
    draw_text("VELMARA", SX0 + SCW / 2, SY0 + 48, 104, PAPER,
              tracking=2.2, shadow=_shade(CORAL, 0.92))
    draw_text("WHERE THE SUN SETS TWICE", SX0 + SCW / 2, SY0 + 196, 25,
              GOLD, tracking=5.2)

    # --- frame: ink keyline with a coral hairline --------------------------
    set_clip(0, 0, W, H)
    t = 4
    fill_rect(FRAME, FRAME, W - 2 * FRAME, t, INK)
    fill_rect(FRAME, H - FRAME - t, W - 2 * FRAME, t, INK)
    fill_rect(FRAME, FRAME, t, H - 2 * FRAME, INK)
    fill_rect(W - FRAME - t, FRAME, t, H - 2 * FRAME, INK)
    t2 = 1.6
    o = LINE - 5
    fill_rect(o, o, W - 2 * o, t2, CORAL)
    fill_rect(o, H - o - t2, W - 2 * o, t2, CORAL)
    fill_rect(o, o, t2, H - 2 * o, CORAL)
    fill_rect(W - o - t2, o, t2, H - 2 * o, CORAL)

# ---------------------------------------------------------------- finish
BAYER = [
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
]


def quantise():
    """Downsample 2x2, add print grain, snap to the palette -> indices."""
    cache = {}
    pal = PALETTE
    rows = []
    amp = 13.0  # grain amplitude in RGB units
    for y in range(H):
        row_idx = bytearray(W)
        by = y * SS
        for x in range(W):
            bx = x * SS
            r = g = b = 0
            for dy in (0, 1):
                srow = buf[by + dy]
                j = bx * 3
                r += srow[j] + srow[j + 3]
                g += srow[j + 1] + srow[j + 4]
                b += srow[j + 2] + srow[j + 5]
            # gentle vignette so the corners settle into the paper
            dx = (x - W / 2) / (W / 2)
            dyv = (y - H / 2) / (H / 2)
            vig = 1.0 - 0.07 * (dx * dx + dyv * dyv) / 2.0
            grain = (BAYER[y & 7][x & 7] - 31.5) / 31.5 * amp
            key = (int(r * 0.25 * vig + grain),
                   int(g * 0.25 * vig + grain),
                   int(b * 0.25 * vig + grain))
            idx = cache.get(key)
            if idx is None:
                best, bd = 0, 1 << 62
                for i, (pr, pg, pb) in enumerate(pal):
                    d = ((key[0] - pr) ** 2 + (key[1] - pg) ** 2
                         + (key[2] - pb) ** 2)
                    if d < bd:
                        bd, best = d, i
                idx = best
                cache[key] = idx
            row_idx[x] = idx
        rows.append(bytes(row_idx))
    return rows


def write_png(rows):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 3, 0, 0, 0)
    plte = b"".join(bytes(c) for c in PALETTE)
    raw = bytearray()
    prev = bytes(W)
    for row in rows:
        # pick the cheapest of filters None / Sub / Up for this row
        cands = []
        sub = bytes((row[i] - (row[i - 1] if i else 0)) & 0xFF
                    for i in range(W))
        up = bytes((row[i] - prev[i]) & 0xFF for i in range(W))
        for ft, data in ((0, row), (1, sub), (2, up)):
            score = sum(v if v < 128 else 256 - v for v in data)
            cands.append((score, ft, data))
        cands.sort(key=lambda c: c[0])
        _, ft, data = cands[0]
        raw.append(ft)
        raw += data
        prev = row
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"PLTE", plte)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(OUT_PATH, "wb") as fh:
        fh.write(png)
    return len(png)


def main():
    paint()
    rows = quantise()
    n = write_png(rows)
    print(f"wrote {OUT_PATH}: {W}x{H}, {n} bytes, "
          f"{len(PALETTE)} palette colours")


if __name__ == "__main__":
    main()
