"""YouTube thumbnails (1280x720) in the channel style — 3 A/B variants."""
import math
import os

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
    g = layer.getchannel("A").filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.8))
    gl = Image.new("RGBA", layer.size, E.C[color] + (0,))
    gl.putalpha(g)
    img.alpha_composite(gl, (x0, y0))
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
    os.makedirs(OUT, exist_ok=True)
    outs = []
    for name, fn in (("thumbnail.jpg", variant_a), ("thumbnail_b.jpg", variant_b), ("thumbnail_c.jpg", variant_c)):
        p = os.path.join(OUT, name)
        fn().convert("RGB").resize((1280, 720), Image.LANCZOS).save(p, quality=93)
        outs.append(p)
    print("\n".join(outs))


if __name__ == "__main__":
    main()
