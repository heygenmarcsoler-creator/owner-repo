"""Drawing engine that reproduces the EuroindexLab look (dark navy grid,
amber / green / red accents, Space Grotesk + JetBrains Mono + Inter)."""
import json
import math
import os
import re
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.environ.get("FONT_DIR", os.path.join(HERE, "fonts"))

C = {
    "bg": (9, 14, 22), "amber": (246, 182, 66), "green": (61, 219, 150),
    "red": (246, 88, 108), "white": (238, 242, 250), "muted": (154, 161, 189),
    "slate": (90, 99, 120), "source": (96, 102, 122), "dark": (14, 18, 28),
    "panel": (17, 23, 35), "line": (34, 42, 58), "soft": (201, 207, 222),
}

CONTENT_TOP, CONTENT_BOTTOM = 70, 835
SOURCE_Y, CAPTION_Y = 872, 952


# ------------------------------------------------------------------ fonts
FONT_FILES = {
    "grotesk": "SpaceGrotesk[wght].ttf",
    "mono": "JetBrainsMono[wght].ttf",
    "inter": "Inter[opsz,wght].ttf",
}


@lru_cache(maxsize=256)
def font(family, size, weight=700):
    f = ImageFont.truetype(os.path.join(FONT_DIR, FONT_FILES[family]), size)
    try:
        axes = f.get_variation_axes()
        vals = []
        for ax in axes:
            name = ax.get("name", b"")
            name = name.decode() if isinstance(name, bytes) else str(name)
            if "eight" in name or name.lower().startswith("wght"):
                vals.append(max(ax["minimum"], min(ax["maximum"], weight)))
            elif "ptical" in name or name.lower().startswith("opsz"):
                vals.append(max(ax["minimum"], min(ax["maximum"], min(size, 32))))
            else:
                vals.append(ax["default"])
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    return f


def text_w(f, s):
    return f.getlength(s)


# ------------------------------------------------------------------ easing
def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = max(0.0, min(1.0, x))
    return 3 * x * x - 2 * x * x * x


# ------------------------------------------------------------------ background
@lru_cache(maxsize=1)
def background():
    import numpy as np
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    base[:] = C["bg"]
    # cool light from the top-left, warm glow bottom-right, vignette
    d1 = np.sqrt(((xx - 380) / 1500) ** 2 + ((yy - 120) / 900) ** 2)
    cool = np.clip(1 - d1, 0, 1) ** 2
    base += cool[..., None] * np.array([6, 12, 22], np.float32)
    d2 = np.sqrt(((xx - 1880) / 700) ** 2 + ((yy - 1060) / 500) ** 2)
    warm = np.clip(1 - d2, 0, 1) ** 2
    base += warm[..., None] * np.array([14, 4, 2], np.float32)
    dv = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.8)) ** 2)
    base *= (1 - 0.35 * np.clip(dv - 0.35, 0, 1))[..., None]
    # faint grid, 80px like the shorts
    grid = np.zeros((H, W), np.float32)
    grid[:, ::80] = 1
    grid[::80, :] = 1
    base += grid[..., None] * np.array([4, 6, 9], np.float32)
    return Image.fromarray(np.clip(base, 0, 255).astype("uint8"), "RGB")


# ------------------------------------------------------------------ markup
MARK = re.compile(r"\{([argm]):([^}]*)\}")
MARK_COL = {"a": "amber", "r": "red", "g": "green", "m": "muted"}


def runs(text, default):
    out, pos = [], 0
    for m in MARK.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], default))
        out.append((m.group(2), MARK_COL[m.group(1)]))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], default))
    return out


def wrap_runs(rs, f, maxw):
    words = []
    for t, col in rs:
        parts = re.split(r"(\s+)", t)
        for p in parts:
            if p == "":
                continue
            words.append((p, col))
    lines, cur, curw = [], [], 0.0
    for wd, col in words:
        ww = text_w(f, wd)
        if wd.isspace():
            if cur:
                cur.append((wd, col)); curw += ww
            continue
        if cur and curw + ww > maxw:
            while cur and cur[-1][0].isspace():
                curw -= text_w(f, cur.pop()[0])
            lines.append(cur); cur, curw = [], 0.0
        cur.append((wd, col)); curw += ww
    while cur and cur[-1][0].isspace():
        cur.pop()
    if cur:
        lines.append(cur)
    return lines


def glow(img, radius=18, strength=0.55):
    a = img.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    a = a.point(lambda v: int(v * strength))
    g = Image.new("RGBA", img.size, (0, 0, 0, 0))
    # tint glow with the dominant colour of the sprite
    rgb = img.convert("RGB").resize((1, 1), Image.BOX, reducing_gap=None)
    bbox = img.getbbox()
    if bbox:
        crop = img.crop(bbox)
        px = crop.convert("RGBA").resize((8, 8), Image.BILINEAR).getdata()
        best = max(px, key=lambda p: p[3] * (max(p[:3]) - min(p[:3]) + 1))
        rgb = best[:3]
    else:
        rgb = (255, 255, 255)
    g.paste(rgb if isinstance(rgb, tuple) else (255, 255, 255), (0, 0, img.size[0], img.size[1]))
    g.putalpha(a)
    return Image.alpha_composite(g, img)


def rich_text(text, size, family="grotesk", weight=700, default="white", maxw=1560,
              align="center", line_gap=1.12, shadow=False):
    f = font(family, size, weight)
    lines = wrap_runs(runs(text, default), f, maxw)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * line_gap)
    widths = [sum(text_w(f, t) for t, _ in ln) for ln in lines]
    w = int(max(widths) if widths else 1) + 8
    h = lh * len(lines) + 8
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (w - widths[i]) / 2 if align == "center" else 0
        y = i * lh
        for t, col in ln:
            d.text((x, y), t, font=f, fill=C[col] + (255,))
            x += text_w(f, t)
    return img


# ------------------------------------------------------------------ elements
def el_key(e):
    return json.dumps({k: v for k, v in e.items() if k not in ("at",)}, sort_keys=True, default=str)


@lru_cache(maxsize=2048)
def sprite_cached(key):
    return build_sprite(json.loads(key))


def fmt_value(e, v):
    s = e["fmt"].format(abs(v) if e["fmt"].startswith("−") else v)
    return s.replace("-", "−")


def build_sprite(e, prog=1.0, now=None):
    k = e["kind"]
    if k == "pill":
        f = font("grotesk", 64, 700)
        tw = text_w(f, e["text"])
        img = Image.new("RGBA", (int(tw) + 70, 104), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, img.width - 1, 103), radius=16, fill=C["amber"] + (255,))
        d.text((35, 14), e["text"], font=f, fill=(20, 18, 14, 255))
        return img
    if k == "tag":
        f = font("mono", 40, 750)
        t = e["text"]
        sp = 6
        tw = sum(text_w(f, ch) + sp for ch in t)
        img = Image.new("RGBA", (int(tw) + 10, 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 4
        col = C[e.get("color", "muted")] + (255,)
        for ch in t:
            d.text((x, 4), ch, font=f, fill=col)
            x += text_w(f, ch) + sp
        return img
    if k == "head":
        return rich_text(e["text"], e.get("size", 72), "grotesk", 700, "white", maxw=1600)
    if k == "sub":
        return rich_text(e["text"], e.get("size", 44), "grotesk", 500, "soft", maxw=1500)
    if k == "big":
        txt = e["text"] if e.get("text") else fmt_value(e, e["to"])
        img = rich_text(txt, e.get("size", 190), "mono", 800, e.get("color", "amber"), maxw=1800)
        pad = 40
        big_img = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
        big_img.paste(img, (pad, pad), img)
        return glow(big_img, 22, 0.5)
    if k == "gap":
        return Image.new("RGBA", (1, e.get("h", 30)), (0, 0, 0, 0))
    if k == "chips":
        f = font("grotesk", 50, 600)
        items = e["items"]
        ws = [text_w(f, t) + 56 for t in items]
        rowsl, cur, curw = [], [], 0
        for t, w_ in zip(items, ws):
            if cur and curw + w_ + 20 > 1500:
                rowsl.append(cur); cur, curw = [], 0
            cur.append((t, w_)); curw += w_ + 20
        rowsl.append(cur)
        tot_w = int(max(sum(w_ for _, w_ in r) + 20 * (len(r) - 1) for r in rowsl)) + 4
        img = Image.new("RGBA", (tot_w, 92 * len(rowsl)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for ri, r in enumerate(rowsl):
            x = (tot_w - (sum(w_ for _, w_ in r) + 20 * (len(r) - 1))) / 2
            y = ri * 92
            for t, w_ in r:
                d.rounded_rectangle((x, y, x + w_, y + 80), radius=40, fill=C["panel"] + (255,),
                                    outline=C["line"] + (255,), width=2)
                d.text((x + 28, y + 12), t, font=f, fill=C["white"] + (255,))
                if e.get("strike"):
                    d.line((x + 10, y + 40, x + w_ - 10, y + 36), fill=C["red"] + (255,), width=6)
                x += w_ + 20
        return img
    if k == "rows":
        return rows_sprite(e["items"])
    if k == "table":
        return table_sprite(e["header"], e["items"])
    if k == "bars":
        return bars_sprite(e["items"], e.get("maxv"), prog)
    if k == "waffle":
        return waffle_sprite(e["groups"], prog)
    if k == "options":
        return options_sprite(e, now)
    if k == "boxes":
        return boxes_sprite(e["items"], e.get("note"))
    if k == "card":
        return card_sprite(e["label"], e["title"])
    if k == "chart":
        return chart_sprite(e, prog)
    raise ValueError(k)


def draw_check(d, x, y, s, col, w=6):
    d.line([(x, y + s * 0.55), (x + s * 0.38, y + s * 0.9), (x + s, y + s * 0.12)], fill=col, width=w, joint="curve")


def rows_sprite(items, width=1320):
    fk = font("grotesk", 50, 500)
    fv = font("mono", 54, 800)
    rh = 102
    img = Image.new("RGBA", (width, rh * len(items)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, (key, val, col) in enumerate(items):
        y = i * rh
        d.rounded_rectangle((0, y + 6, width - 1, y + rh - 6), radius=14,
                            fill=C["panel"] + (235,), outline=C["line"] + (255,), width=2)
        d.text((36, y + 22), key, font=fv if len(key) <= 2 else fk, fill=C["soft"] + (255,))
        if val == "✓":
            draw_check(d, width - 36 - 40, y + 30, 40, C.get(col, C["white"]) + (255,), 7)
            continue
        if len(key) <= 2:  # numbered checklist: value left-aligned after the number
            d.text((96, y + 22), val, font=fk, fill=C.get(col, C["white"]) + (255,))
            continue
        vw = text_w(fv, val)
        d.text((width - 36 - vw, y + 19), val, font=fv, fill=C.get(col, C["white"]) + (255,))
    return img


def table_sprite(header, items, width=1400):
    fk = font("grotesk", 50, 500)
    fh = font("mono", 46, 800)
    fv = font("mono", 54, 800)
    cols = [0.0, 0.62, 0.84]
    rh = 100
    img = Image.new("RGBA", (width, rh * (len(items) + 1) + 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for j, htxt in enumerate(header):
        if htxt:
            cx = width * (cols[j] + (0.11 if j else 0))
            col = C["muted"] if j == 1 else C["amber"]
            d.text((cx - text_w(fh, htxt) / 2, 20), htxt, font=fh, fill=col + (255,))
    d.line((0, rh, width, rh), fill=C["line"] + (255,), width=2)
    for i, (k, a, b) in enumerate(items):
        y = rh * (i + 1)
        d.text((24, y + 22), k, font=fk, fill=C["soft"] + (255,))
        for j, v in ((1, a), (2, b)):
            cx = width * (cols[j] + 0.11)
            col = C["muted"] if j == 1 else C["red"]
            d.text((cx - text_w(fv, v) / 2, y + 18), v, font=fv, fill=col + (255,))
        d.line((0, y + rh, width, y + rh), fill=C["line"] + (160,), width=1)
    return img


def bars_sprite(items, maxv, prog=1.0, width=1580):
    fl = font("grotesk", 46, 500)
    fv = font("mono", 50, 800)
    maxv = maxv or max(v for _, v, _, _ in items) * 1.1
    lab_w = 630
    bar_w = width - lab_w - 230
    rh = 92
    img = Image.new("RGBA", (width, rh * len(items)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = ease_out(prog)
    for i, (lab, v, disp, col) in enumerate(items):
        y = i * rh
        d.text((lab_w - 26 - text_w(fl, lab), y + 18), lab, font=fl, fill=C["soft"] + (255,))
        d.rounded_rectangle((lab_w, y + 24, lab_w + bar_w, y + rh - 24), radius=8, fill=C["panel"] + (255,))
        bw = max(8, bar_w * min(1, v / maxv) * p)
        d.rounded_rectangle((lab_w, y + 24, lab_w + bw, y + rh - 24), radius=8, fill=C[col] + (255,))
        if p > 0.3:
            a = int(255 * min(1, (p - 0.3) / 0.4))
            d.text((lab_w + bw + 20, y + 16), disp, font=fv, fill=C[col if col != "slate" else "muted"] + (a,))
    return img


def waffle_sprite(groups, prog=1.0):
    n = 100
    cols_ = []
    for cnt, col, _ in groups:
        cols_ += [col] * cnt
    cols_ = (cols_ + ["slate"] * n)[:n]
    sq, gp = 50, 10
    gw = 10 * sq + 9 * gp
    legend = [(c, l) for _, c, l in groups if l]
    fl = font("grotesk", 38, 500)
    lw = 0
    if legend:
        lw = 60 + max(text_w(fl, f"€{cn}  {l}") for cn, _, l in groups if l) + 40
    img = Image.new("RGBA", (gw + (int(lw) + 60 if legend else 0), gw), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = ease_out(prog)
    for i in range(n):
        r, c = divmod(i, 10)
        x, y = c * (sq + gp), r * (sq + gp)
        col = cols_[i]
        filled = i < p * n * 1.0001
        base = C["slate"] if (not filled or col == "slate") else C[col]
        alpha = 255 if col != "slate" else 140
        d.rounded_rectangle((x, y, x + sq, y + sq), radius=6, fill=base + (alpha,))
    if legend:
        lx = gw + 70
        ly = gw / 2 - len(legend) * 70 / 2
        for i, (col, lab) in enumerate(legend):
            cnt = next(cn for cn, c2, l2 in groups if l2 == lab)
            y = ly + i * 70
            d.rounded_rectangle((lx, y + 8, lx + 34, y + 42), radius=6, fill=C[col] + (255,))
            d.text((lx + 52, y), f"€{cnt}  {lab}", font=fl, fill=C["soft"] + (255,))
    return img


def options_sprite(e, now):
    # now = dict(t_since_show, revealed(bool), t_since_reveal)
    items = e["items"]
    f = font("mono", 52, 800)
    fl = font("mono", 46, 800)
    ow, oh = 860, 92
    countdown = e.get("countdown") and now is not None and not now.get("revealed")
    extra = 150 if e.get("countdown") else 0
    img = Image.new("RGBA", (ow, oh * len(items) + 20 * (len(items) - 1) + extra), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    revealed = now and now.get("revealed")
    for i, t in enumerate(items):
        y = i * (oh + 20)
        stagger = 1.0 if now is None else min(1, max(0, (now["t"] - i * 0.15) / 0.3))
        if stagger <= 0:
            continue
        a = int(255 * stagger)
        correct = revealed and e.get("correct") == i
        dim = revealed and e.get("correct") is not None and not correct
        if correct:
            d.rounded_rectangle((0, y, ow, y + oh), radius=12, fill=C["green"] + (a,))
            d.text((28, y + 14), "ABC"[i], font=fl, fill=(10, 30, 20, a))
            d.text((90, y + 12), t, font=f, fill=(10, 30, 20, a))
            draw_check(d, ow - 70, y + 24, 40, (10, 30, 20, a), 7)
        else:
            aa = int(a * (0.35 if dim else 1))
            d.rounded_rectangle((0, y, ow, y + oh), radius=12, fill=C["panel"] + (aa,),
                                outline=C["soft"] + (int(aa * 0.8),), width=2)
            d.text((28, y + 14), "ABC"[i], font=fl, fill=C["amber"] + (aa,))
            d.text((90, y + 12), t, font=f, fill=C["white"] + (aa,))
    if countdown and now["t"] > 0.6:
        tt = now["t"] - 0.6
        if tt < 3.0:
            num = 3 - int(tt)
            frac = tt - int(tt)
            cx, cy, r = ow / 2, img.height - 66, 52
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=C["line"] + (255,), width=8)
            col = C["amber"] if num > 1 else C["red"]
            d.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * (1 - frac), fill=col + (255,), width=8)
            fn = font("mono", 54, 800)
            s = str(num)
            d.text((cx - text_w(fn, s) / 2, cy - 36), s, font=fn, fill=col + (255,))
    return img


def boxes_sprite(items, note):
    f = font("mono", 84, 800)
    s, gp = 130, 30
    tw = len(items) * s + (len(items) - 1) * gp
    img = Image.new("RGBA", (max(tw, 520), s + 90), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (img.width - tw) / 2
    for i, t in enumerate(items):
        x = x0 + i * (s + gp)
        d.rounded_rectangle((x, 0, x + s, s), radius=18, outline=C["amber"] + (255,), width=5,
                            fill=C["panel"] + (200,))
        d.text((x + s / 2 - text_w(f, t) / 2, 10), t, font=f, fill=C["amber"] + (255,))
    if note:
        fn = font("grotesk", 38, 500)
        nt = note + "  ↓"
        d.text((img.width / 2 - text_w(fn, nt) / 2, s + 30), nt, font=fn, fill=C["soft"] + (255,))
    return img


def card_sprite(label, title):
    fl = font("mono", 40, 800)
    ft = font("grotesk", 56, 700)
    lines = wrap_runs([(title, "white")], ft, 1000)
    bw = 1120
    bh = 70 * len(lines) + 70
    img = Image.new("RGBA", (bw, bh + 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    sp = 8
    lw = sum(text_w(fl, ch) + sp for ch in label)
    x = bw / 2 - lw / 2
    for ch in label:
        d.text((x, 0), ch, font=fl, fill=C["amber"] + (255,))
        x += text_w(fl, ch) + sp
    d.rounded_rectangle((0, 70, bw, 70 + bh), radius=18, fill=C["panel"] + (255,), outline=C["line"] + (255,), width=2)
    for i, ln in enumerate(lines):
        t = "".join(w for w, _ in ln)
        d.text((bw / 2 - text_w(ft, t) / 2, 70 + 32 + i * 70), t, font=ft, fill=C["white"] + (255,))
    cy = 70 + bh + 60
    d.polygon([(bw / 2 - 26, cy), (bw / 2 + 26, cy), (bw / 2, cy + 40)], fill=C["amber"] + (255,))
    return img


# ------------------------------------------------------------------ chart
def fmt_k(v):
    if v >= 100000:
        return f"€{v / 1000:.0f}k"
    if v >= 10000:
        return f"€{v / 1000:.1f}k".replace(".0k", "k")
    return f"€{v / 1000:.1f}k"


def chart_sprite(e, prog=1.0, width=1400, height=None):
    height = e.get("h", 400)
    S = 2  # supersampling
    pad_l, pad_r, pad_t, pad_b = 150, 190, 30, 70
    Wc, Hc = width * S, (height + pad_t + pad_b) * S
    img = Image.new("RGBA", (Wc, Hc), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, x1 = e["xr"]
    y0, y1 = e["yr"]
    pw, ph = (width - pad_l - pad_r) * S, height * S

    def X(x):
        return (pad_l * S) + (x - x0) / (x1 - x0) * pw

    def Y(y):
        return pad_t * S + ph - (y - y0) / (y1 - y0) * ph

    fy = font("mono", 26 * S, 600)
    for val, lab in e.get("yticks", []):
        yy = Y(val)
        d.line((pad_l * S, yy, pad_l * S + pw, yy), fill=C["line"] + (255,), width=2 * S // 2)
        d.text((pad_l * S - 20 * S - text_w(fy, lab), yy - 18 * S), lab, font=fy, fill=C["muted"] + (255,))
    if e.get("ref") is not None:
        yy = Y(e["ref"])
        xx = pad_l * S
        while xx < pad_l * S + pw:
            d.line((xx, yy, min(xx + 18 * S, pad_l * S + pw), yy), fill=C["slate"] + (255,), width=3 * S // 2)
            xx += 30 * S
    for xt in e.get("xticks", []):
        lab = str(xt)
        d.text((X(xt) - text_w(fy, lab) / 2, pad_t * S + ph + 22 * S), lab, font=fy, fill=C["muted"] + (255,))

    line_layer = Image.new("RGBA", (Wc, Hc), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line_layer)
    labels = []
    for s in e["series"]:
        xs, ys = s["x"], s["y"]
        upto = s.get("upto", xs[-1])
        frm = s.get("frm")
        lim = upto if frm is None or prog >= 1 else frm + (upto - frm) * ease_in_out(prog)
        if frm is None and prog < 1:
            lim = xs[0] + (upto - xs[0]) * ease_in_out(prog)
        pts = []
        for i, (x, y) in enumerate(zip(xs, ys)):
            if x <= lim + 1e-9:
                pts.append((X(x), Y(y)))
            else:
                if i > 0 and xs[i - 1] < lim:
                    fx = (lim - xs[i - 1]) / (x - xs[i - 1])
                    yi = ys[i - 1] + (y - ys[i - 1]) * fx
                    pts.append((X(lim), Y(yi)))
                break
        if len(pts) < 2:
            continue
        col = C[s.get("color", "amber")]
        ld.line(pts, fill=col + (255,), width=7 * S, joint="curve")
        r = 10 * S
        ex, ey = pts[-1]
        ld.ellipse((ex - r, ey - r, ex + r, ey + r), fill=col + (255,))
        if s.get("end_label"):
            # value at the end of the drawn part
            xe = (ex - pad_l * S) / pw * (x1 - x0) + x0
            ye = y0 + (pad_t * S + ph - ey) / ph * (y1 - y0)
            labels.append((ex, ey, fmt_k(ye), col))
    gl = line_layer.getchannel("A").filter(ImageFilter.GaussianBlur(10 * S))
    gl = gl.point(lambda v: int(v * 0.6))
    glow_l = Image.new("RGBA", (Wc, Hc), C["amber"] + (0,))
    glow_l.putalpha(gl)
    img = Image.alpha_composite(img, glow_l)
    img = Image.alpha_composite(img, line_layer)
    d = ImageDraw.Draw(img)
    fe = font("mono", 32 * S, 700)
    for ex, ey, lab, col in labels:
        d.line((ex + 16 * S, ey, ex + 34 * S, ey), fill=C["muted"] + (255,), width=2 * S)
        d.text((ex + 42 * S, ey - 22 * S), lab, font=fe, fill=C["white"] + (255,))
    return img.resize((width, height + pad_t + pad_b), Image.LANCZOS)


# ------------------------------------------------------------------ captions
@lru_cache(maxsize=4096)
def caption_sprite(words, active):
    f = font("grotesk", 64, 600)
    words = list(words)
    sp = text_w(f, " ")
    widths = [text_w(f, w) for w in words]
    tw = sum(widths) + sp * (len(words) - 1)
    pad = 16
    img = Image.new("RGBA", (int(tw) + 2 * pad, 100), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    d = ImageDraw.Draw(img)
    x = pad
    for i, w in enumerate(words):
        ds.text((x + 3, 12 + 6), w, font=f, fill=(0, 0, 0, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))
        x += widths[i] + sp
    sh = sh.filter(ImageFilter.GaussianBlur(2))
    x = pad
    for i, w in enumerate(words):
        col = C["amber"] if i == active else C["white"]
        d.text((x, 12), w, font=f, fill=col + (255,), stroke_width=2, stroke_fill=(0, 0, 0, 255))
        x += widths[i] + sp
    return Image.alpha_composite(sh, img)


@lru_cache(maxsize=512)
def source_sprite(text):
    f = font("inter", 26, 400)
    w = int(text_w(f, text)) + 10
    img = Image.new("RGBA", (w, 40), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((5, 4), text, font=f, fill=C["source"] + (255,))
    return img
