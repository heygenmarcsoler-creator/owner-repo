"""YouTube thumbnails (1280x720) in the channel style — 3 A/B variants."""
import math
import os

import numpy as np

from PIL import Image, ImageDraw, ImageFilter

import engine as E
from script import X, WORLD

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
W, H = 1920, 1080


def base():
    img = E.background_at(0).copy()
    # stronger vignette + warm red glow for drama
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((900, 250, 2300, 1400), fill=(246, 88, 108, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    return img


def text(img, s, size, xy, family="grotesk", weight=700, default="white", anchor="l", glow_=False, shadow=True):
    spr = E.rich_text(s, size, family, weight, default, maxw=1900, align="left" if anchor == "l" else "center")
    if glow_:
        pad = 50
        big = Image.new("RGBA", (spr.width + 2 * pad, spr.height + 2 * pad), (0, 0, 0, 0))
        big.paste(spr, (pad, pad), spr)
        spr = E.glow(big, 26, 0.7)
        xy = (xy[0] - pad, xy[1] - pad)
    if shadow:
        sh = Image.new("RGBA", spr.size, (0, 0, 0, 0))
        sh.putalpha(spr.getchannel("A").point(lambda v: int(v * 0.85)))
        sh = sh.filter(ImageFilter.GaussianBlur(6))
        img.alpha_composite(sh, (int(xy[0] + 6 - (spr.width / 2 if anchor == "c" else 0)), int(xy[1] + 10)))
    x = xy[0] - (spr.width / 2 if anchor == "c" else 0)
    img.alpha_composite(spr, (int(x), int(xy[1])))
    return spr.size


def crash_line(img, box, upto=2008.0, color="red", width=16):
    x0, y0, x1, y1 = box
    S = 2
    layer = Image.new("RGBA", ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    xs = [x for x in X if x <= upto]
    ys = WORLD[:len(xs)]
    lo, hi = 4500, 10500
    m = 40 * S
    pts = [(m + (x - X[0]) / (upto - X[0]) * ((x1 - x0) * S - 2 * m), m + (1 - (y - lo) / (hi - lo)) * ((y1 - y0) * S - 2 * m))
           for x, y in zip(xs, ys)]
    d.line(pts, fill=E.C[color] + (255,), width=width * S, joint="curve")
    ex, ey = pts[-1]
    r = 22 * S
    d.ellipse((ex - r, ey - r, ex + r, ey + r), fill=E.C[color] + (255,))
    layer = layer.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    P = 70  # room for the glow, so it is not cut into a square at the box edge
    padded = Image.new("RGBA", (layer.width + 2 * P, layer.height + 2 * P), (0, 0, 0, 0))
    padded.alpha_composite(layer, (P, P))
    g = padded.getchannel("A").filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.8))
    gl = Image.new("RGBA", padded.size, E.C[color] + (0,))
    gl.putalpha(g)
    img.alpha_composite(gl.crop((max(0, P - x0), max(0, P - y0), gl.width, gl.height)), (max(0, x0 - P), max(0, y0 - P)))
    img.alpha_composite(layer, (x0, y0))
    # dashed €10k reference
    d2 = ImageDraw.Draw(img)
    yr = y0 + 40 + (1 - (10000 - lo) / (hi - lo)) * (y1 - y0 - 80)
    x = x0
    while x < x1:
        d2.line((x, yr, min(x + 30, x1), yr), fill=(120, 130, 155, 255), width=5)
        x += 50


def stamp(img, s, xy, size=110, color="red", angle=8):
    spr = E.build_sprite(dict(kind="stamp", text=s, color=color, angle=angle, size=size))
    img.alpha_composite(spr, (int(xy[0] - spr.width / 2), int(xy[1] - spr.height / 2)))


def bar(img):
    ImageDraw.Draw(img).rectangle((0, 0, W, 16), fill=E.C["amber"])


def variant_a():
    """Big red -45% + crash line + 'AI = 2000?'"""
    img = base()
    crash_line(img, (980, 330, 1860, 900), upto=2002.0)
    text(img, "AI = {a:2000?}", 190, (80, 90))
    text(img, "−45%", 330, (60, 400), family="mono", weight=800, default="red", glow_=True)
    stamp(img, "YOUR WORLD ETF", (1420, 930), size=72, color="amber", angle=-5)
    bar(img)
    return img


def variant_b():
    """'13 YEARS' to get your money back."""
    img = base()
    crash_line(img, (1000, 380, 1860, 860), upto=2013.0, color="amber", width=14)
    text(img, "€10,000 →", 120, (80, 110), family="mono", weight=800)
    text(img, "13", 470, (60, 250), family="mono", weight=800, default="red", glow_=True)
    text(img, "YEARS", 150, (95, 790), family="grotesk", weight=700)
    stamp(img, "AI BUBBLE?", (1430, 200), size=96, color="red", angle=6)
    bar(img)
    return img


def _smooth(pts, n=24):
    """Monotone cubic (Fritsch-Carlson) through the yearly points: smooth, never overshoots the data."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    k = len(pts)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(k - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, k - 1)] + [d[-1]]
    for i in range(k - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            r = a * a + b * b
            if r > 9:
                t = 3 / math.sqrt(r)
                m[i], m[i + 1] = t * a * d[i], t * b * d[i]
    out = []
    for i in range(k - 1):
        h = xs[i + 1] - xs[i]
        for j in range(n):
            t = j / n
            h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
            out.append((xs[i] + t * h, h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]))
    out.append(pts[-1])
    return out


def _glow(layer, radius, strength):
    g = layer.filter(ImageFilter.GaussianBlur(radius))
    a = g.getchannel("A").point(lambda v: int(min(255, v * strength)))
    g.putalpha(a)
    return g


def variant_v4():
    """v4: €10,000 at the 1999 top, 13 years under water. Big chart, red 'under water' area, no top bar."""
    from data import MSCI_WORLD_EUR, lump_sum_path
    S = 2
    Wt, Ht = 1920 * S, 1080 * S
    red, red_dk, green, white = (248, 82, 104), (190, 24, 52), (52, 211, 140), (241, 245, 250)
    # background: navy gradient, red glow behind the hole, vignette
    yy, xx = np.mgrid[0:Ht, 0:Wt].astype(np.float32)
    bg = np.zeros((Ht, Wt, 3), np.float32)
    t = (yy / Ht)[..., None]
    bg[:] = np.array([13, 18, 30]) * (1 - t) + np.array([6, 8, 13]) * t
    d = np.sqrt(((xx - Wt * 0.66) / (Wt * 0.42)) ** 2 + ((yy - Ht * 0.72) / (Ht * 0.55)) ** 2)
    bg += (np.clip(1 - d, 0, 1) ** 2)[..., None] * np.array([70, 10, 22])
    dv = np.sqrt(((xx - Wt / 2) / (Wt * 0.62)) ** 2 + ((yy - Ht / 2) / (Ht * 0.7)) ** 2)
    bg *= (1 - 0.55 * np.clip(dv - 0.55, 0, 1))[..., None]
    img = Image.fromarray(np.clip(bg, 0, 255).astype("uint8"), "RGB").convert("RGBA")
    # chart geometry
    vals = [round(v) for v in lump_sum_path(MSCI_WORLD_EUR)[:15]]  # 1999 .. 2013
    years = list(range(1999, 2014))
    cx0, cx1, cy0, cy1 = 1010 * S, 1860 * S, 150 * S, 940 * S
    lo, hi = 4300, 11600
    X_ = lambda y: cx0 + (y - 1999) / (2013 - 1999) * (cx1 - cx0)
    Y_ = lambda v: cy0 + (1 - (v - lo) / (hi - lo)) * (cy1 - cy0)
    base_y = Y_(10000)
    pts = _smooth([(X_(y), Y_(v)) for y, v in zip(years, vals)])
    # faint grid inside the chart
    grid = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for v in range(5000, 11001, 1000):
        gd.line((cx0, Y_(v), cx1, Y_(v)), fill=(255, 255, 255, 14), width=2 * S)
    img.alpha_composite(grid)
    # under-water area: between the €10k line and the curve, red fading downwards
    area = Image.new("L", img.size, 0)
    ImageDraw.Draw(area).polygon([(cx0, base_y)] + pts + [(pts[-1][0], base_y)], fill=255)
    below = Image.new("L", img.size, 0)
    ImageDraw.Draw(below).rectangle((0, int(base_y), Wt, Ht), fill=255)
    mask = Image.fromarray((np.asarray(area, np.float32) * np.asarray(below, np.float32) / 255).astype("uint8"))
    grad = np.clip((yy - base_y) / (Y_(5300) - base_y), 0, 1)
    fill_a = (np.asarray(mask, np.float32) / 255) * (60 + 120 * grad)
    fill = np.zeros((Ht, Wt, 4), np.uint8)
    fill[..., :3] = red_dk
    fill[..., 3] = np.clip(fill_a, 0, 255).astype("uint8")
    img.alpha_composite(Image.fromarray(fill, "RGBA"))
    # €10k reference line (dashed)
    ref = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ref)
    x = cx0 - 30 * S
    while x < cx1 + 40 * S:
        rd.line((x, base_y, min(x + 26 * S, cx1 + 40 * S), base_y), fill=(226, 232, 240, 150), width=4 * S)
        x += 44 * S
    img.alpha_composite(ref)
    # the line: red while under water, green once it is back above €10k
    cross = next(i for i, p in enumerate(pts) if i > len(pts) // 2 and p[1] <= base_y)
    line = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(line)
    ld.line(pts[:cross + 1], fill=red + (255,), width=13 * S, joint="curve")
    ld.line(pts[cross:], fill=green + (255,), width=13 * S, joint="curve")
    img.alpha_composite(_glow(line, 26 * S, 1.6))
    img.alpha_composite(line)
    # dots: start, low point, end
    dots = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    sx, sy = pts[0]
    dd.ellipse((sx - 15 * S, sy - 15 * S, sx + 15 * S, sy + 15 * S), fill=white + (255,))
    ex, ey = pts[-1]
    dd.ellipse((ex - 40 * S, ey - 40 * S, ex + 40 * S, ey + 40 * S), fill=green + (70,))
    dd.ellipse((ex - 22 * S, ey - 22 * S, ex + 22 * S, ey + 22 * S), fill=green + (255,))
    dd.ellipse((ex - 9 * S, ey - 9 * S, ex + 9 * S, ey + 9 * S), fill=white + (255,))
    img.alpha_composite(_glow(dots, 18 * S, 1.2))
    img.alpha_composite(dots)
    # −45% pill under the 2002 low
    lx, ly = X_(2002), Y_(vals[3])
    fp = E.font("mono", 64 * S, 800)
    txt = "−45%"
    tw_ = ImageDraw.Draw(img).textlength(txt, font=fp)
    pw, ph = tw_ + 56 * S, 100 * S
    pill = Image.new("RGBA", img.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    px, py = lx - pw / 2, ly + 46 * S
    pd.rounded_rectangle((px, py, px + pw, py + ph), radius=ph / 2, fill=red + (255,))
    pd.text((px + 28 * S, py + 12 * S), txt, font=fp, fill=white + (255,))
    img.alpha_composite(_glow(pill, 20 * S, 0.9))
    img.alpha_composite(pill)
    # headline: giant 13 with a red gradient + glow, YEARS in white
    f13 = E.font("inter", 600 * S, 900)
    m13 = Image.new("L", img.size, 0)
    ImageDraw.Draw(m13).text((70 * S, 50 * S), "13", font=f13, fill=255)
    g = np.clip((yy - 150 * S) / (650 * S), 0, 1)[..., None]
    col = np.array([255, 120, 138], np.float32) * (1 - g) + np.array([214, 30, 62], np.float32) * g
    t13 = np.zeros((Ht, Wt, 4), np.uint8)
    t13[..., :3] = col.astype("uint8")
    t13[..., 3] = np.asarray(m13)
    t13 = Image.fromarray(t13, "RGBA")
    img.alpha_composite(_glow(t13, 40 * S, 0.8))
    img.alpha_composite(t13)
    fy = E.font("inter", 190 * S, 900)
    yrs = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(yrs).text((86 * S, 770 * S), "YEARS", font=fy, fill=white + (255,))
    sh2 = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh2.putalpha(yrs.getchannel("A").point(lambda v: int(v * 0.75)))
    img.alpha_composite(sh2.filter(ImageFilter.GaussianBlur(14 * S)), (6 * S, 12 * S))
    img.alpha_composite(yrs)
    return img.resize((1920, 1080), Image.LANCZOS)


def variant_v5():
    """v5: Trump wanted 1% (struck out) -> the Fed went to 4%. Fed funds step chart glowing behind."""
    from script_v5 import FED_X, FED_Y
    S = 2
    Wt, Ht = 1920 * S, 1080 * S
    red, slate, amber, white = (248, 82, 104), (120, 132, 156), (245, 158, 11), (241, 245, 250)
    yy, xx = np.mgrid[0:Ht, 0:Wt].astype(np.float32)
    bg = np.zeros((Ht, Wt, 3), np.float32)
    t = (yy / Ht)[..., None]
    bg[:] = np.array([13, 18, 30]) * (1 - t) + np.array([6, 8, 13]) * t
    d = np.sqrt(((xx - Wt * 0.74) / (Wt * 0.38)) ** 2 + ((yy - Ht * 0.48) / (Ht * 0.6)) ** 2)
    bg += (np.clip(1 - d, 0, 1) ** 2)[..., None] * np.array([75, 12, 26])
    dv = np.sqrt(((xx - Wt / 2) / (Wt * 0.62)) ** 2 + ((yy - Ht / 2) / (Ht * 0.7)) ** 2)
    bg *= (1 - 0.55 * np.clip(dv - 0.55, 0, 1))[..., None]
    img = Image.fromarray(np.clip(bg, 0, 255).astype("uint8"), "RGB").convert("RGBA")
    # Fed funds path behind the numbers (2022 -> Oct 2026), the last step up in red
    cx0, cx1, cy0, cy1 = 60 * S, 1860 * S, 560 * S, 1010 * S
    X_ = lambda x: cx0 + (x - FED_X[0]) / (FED_X[-1] - FED_X[0]) * (cx1 - cx0)
    Y_ = lambda v: cy1 - v / 6 * (cy1 - cy0)
    pts = [(X_(x), Y_(y)) for x, y in zip(FED_X, FED_Y)]
    k = next(i for i in range(len(FED_X)) if FED_X[i] >= 2026.7)
    line = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(line)
    ld.line(pts[:k + 1], fill=amber + (210,), width=9 * S, joint="curve")
    ld.line(pts[k:], fill=red + (255,), width=12 * S, joint="curve")
    ex, ey = pts[-1]
    ld.ellipse((ex - 22 * S, ey - 22 * S, ex + 22 * S, ey + 22 * S), fill=red + (255,))
    # Trump's 1% as a dashed line
    x = cx0
    while x < cx1:
        ld.line((x, Y_(1.0), min(x + 26 * S, cx1), Y_(1.0)), fill=(226, 232, 240, 110), width=4 * S)
        x += 46 * S
    img.alpha_composite(_glow(line, 24 * S, 1.3))
    img.alpha_composite(line)
    # "1%" struck out
    f1 = E.font("inter", 400 * S, 900)
    one = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(one)
    od.text((90 * S, 40 * S), "1%", font=f1, fill=slate + (255,))
    bb = od.textbbox((90 * S, 40 * S), "1%", font=f1)
    yc = (bb[1] + bb[3]) / 2
    strike = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(strike).line((bb[0] - 20 * S, yc + 50 * S, bb[2] + 20 * S, yc - 50 * S), fill=red + (255,), width=34 * S)
    img.alpha_composite(one)
    img.alpha_composite(_glow(strike, 18 * S, 1.0))
    img.alpha_composite(strike)
    # arrow
    fa = E.font("inter", 230 * S, 800)
    arr = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(arr).text((bb[2] + 50 * S, 120 * S), "→", font=fa, fill=white + (255,))
    img.alpha_composite(arr)
    # "4%" big, red gradient + glow
    f4 = E.font("inter", 500 * S, 900)
    m4 = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(m4)
    b4 = md.textbbox((0, 0), "4%", font=f4)
    md.text((1870 * S - b4[2], -10 * S), "4%", font=f4, fill=255)
    g = np.clip((yy - 80 * S) / (520 * S), 0, 1)[..., None]
    col = np.array([255, 120, 138], np.float32) * (1 - g) + np.array([214, 30, 62], np.float32) * g
    t4 = np.zeros((Ht, Wt, 4), np.uint8)
    t4[..., :3] = col.astype("uint8")
    t4[..., 3] = np.asarray(m4)
    t4 = Image.fromarray(t4, "RGBA")
    img.alpha_composite(_glow(t4, 44 * S, 0.9))
    img.alpha_composite(t4)
    return img.resize((1920, 1080), Image.LANCZOS)


def variant_c():
    """Versus: panic seller vs patient investor."""
    img = base()
    text(img, "AI CRASH: {a:WHO WINS?}", 130, (W / 2, 70), anchor="c")
    for side, (lab, val, col) in enumerate([("SOLD", "€8,813", "red"), ("WAITED", "€46,032", "green")]):
        cx = W * (0.25 if side == 0 else 0.75)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((cx - 350, 300, cx + 350, 900), radius=36, fill=E.C["panel"] + (240,),
                            outline=E.C[col] + (255,), width=8)
        text(img, lab, 110, (cx, 350), family="mono", weight=800, default="muted", anchor="c", shadow=False)
        text(img, val, 125 if side else 140, (cx, 550), family="mono", weight=800, default=col, anchor="c", glow_=True)
    d = ImageDraw.Draw(img)
    d.ellipse((W / 2 - 110, 490, W / 2 + 110, 710), fill=E.C["amber"])
    text(img, "VS", 110, (W / 2, 528), anchor="c", default="white", shadow=False)
    stamp(img, "SAME €10,000", (W / 2, 975), size=70, color="amber", angle=-3)
    bar(img)
    return img


def main():
    import sys
    os.makedirs(OUT, exist_ok=True)
    outs = []
    variants = (("thumbnail.jpg", variant_a), ("thumbnail_b.jpg", variant_b), ("thumbnail_c.jpg", variant_c),
                ("thumbnail_v4.jpg", variant_v4), ("thumbnail_v5.jpg", variant_v5))
    only = sys.argv[1:]
    for name, fn in [v for v in variants if not only or v[0].split(".")[0].split("_")[-1] in only]:
        p = os.path.join(OUT, name)
        size = (1920, 1080) if name in ("thumbnail_v4.jpg", "thumbnail_v5.jpg") else (1280, 720)
        fn().convert("RGB").resize(size, Image.LANCZOS).save(p, quality=93)
        outs.append(p)
    print("\n".join(outs))


if __name__ == "__main__":
    main()
