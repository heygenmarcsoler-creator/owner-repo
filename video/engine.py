"""Drawing engine that reproduces the EuroindexLab look (dark navy grid,
amber / green / red accents, Space Grotesk + JetBrains Mono + Inter)."""
import json
import math
import os
import re
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

VERTICAL = bool(os.environ.get("VERTICAL"))
W, H, FPS = (1080, 1920, 30) if VERTICAL else (1920, 1080, 30)
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.environ.get("FONT_DIR", os.path.join(HERE, "fonts"))

C = {
    "bg": (9, 14, 22), "amber": (246, 182, 66), "green": (61, 219, 150),
    "red": (246, 88, 108), "white": (238, 242, 250), "muted": (154, 161, 189),
    "slate": (90, 99, 120), "source": (96, 102, 122), "dark": (14, 18, 28),
    "panel": (17, 23, 35), "line": (34, 42, 58), "soft": (201, 207, 222),
}

if VERTICAL:
    CONTENT_TOP, CONTENT_BOTTOM = 180, 1220
    SOURCE_Y, CAPTION_Y = 1262, 1350
else:
    CONTENT_TOP, CONTENT_BOTTOM = 70, 835
    SOURCE_Y, CAPTION_Y = 872, 952
TEXT_MAXW = W - 120


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
        return rich_text(e["text"], e.get("size", 72), "grotesk", 700, "white", maxw=min(1600, TEXT_MAXW))
    if k == "sub":
        return rich_text(e["text"], e.get("size", 44), "grotesk", 500, "soft", maxw=min(1500, TEXT_MAXW))
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
        f = font("grotesk", 60, 600)
        items = e["items"]
        ws = [text_w(f, t) + 64 for t in items]
        rowsl, cur, curw = [], [], 0
        for t, w_ in zip(items, ws):
            if cur and curw + w_ + 20 > min(1500, TEXT_MAXW):
                rowsl.append(cur); cur, curw = [], 0
            cur.append((t, w_)); curw += w_ + 20
        rowsl.append(cur)
        tot_w = int(max(sum(w_ for _, w_ in r) + 20 * (len(r) - 1) for r in rowsl)) + 4
        img = Image.new("RGBA", (tot_w, 108 * len(rowsl)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        shown = len(items) if prog >= 1 else int(prog * len(items) + 0.999)
        idx = 0
        for ri, r in enumerate(rowsl):
            x = (tot_w - (sum(w_ for _, w_ in r) + 20 * (len(r) - 1))) / 2
            y = ri * 108
            for t, w_ in r:
                idx += 1
                if idx > shown:
                    break
                d.rounded_rectangle((x, y, x + w_, y + 94), radius=47, fill=C["panel"] + (255,),
                                    outline=C["line"] + (255,), width=2)
                d.text((x + 32, y + 12), t, font=f, fill=C["white"] + (255,))
                if e.get("strike"):
                    d.line((x + 10, y + 50, x + w_ - 10, y + 44), fill=C["red"] + (255,), width=8)
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
    if k in EXTRA_KINDS:
        return EXTRA_KINDS[k](e, prog, now)
    raise ValueError(k)


def draw_check(d, x, y, s, col, w=6):
    d.line([(x, y + s * 0.55), (x + s * 0.38, y + s * 0.9), (x + s, y + s * 0.12)], fill=col, width=w, joint="curve")


def rows_sprite(items, width=None):
    width = width or min(1320, W - 60)
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


def chart_sprite(e, prog=1.0, width=None, height=None):
    width = width or min(1400, W - 30)
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
    f = font("grotesk", 76 if VERTICAL else 64, 600)
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



# ================================================================== v2: extra elements
def ease_out_back(x, s=1.9):
    x = max(0.0, min(1.0, x))
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def spaced(d, xy, text, f, fill, sp=6):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += text_w(f, ch) + sp
    return x


def spaced_w(f, text, sp=6):
    return sum(text_w(f, ch) + sp for ch in text) - sp


CH_TITLES = []  # filled by build.py from script.CH


def chapter_card_sprite(e, prog=1.0, now=None):
    """Big animated chapter opener: number slides in, title wipes, 7 progress dots."""
    t = 99 if now is None else now.get("t", 99)
    i, title = e["n"], e["title"]
    W2, H2 = 1700, 640
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fl = font("mono", 40, 800)
    lab = "CHAPTER"
    a1 = ease_out(t / 0.3)
    spaced(d, (W2 / 2 - spaced_w(fl, lab, 10) / 2, 20), lab, fl, C["muted"] + (int(255 * a1),), 10)
    # number
    num = f"{i:02d}"
    fn = font("mono", 280, 800)
    p = ease_out_back(t / 0.55)
    ni = Image.new("RGBA", (int(text_w(fn, num)) + 120, 380), (0, 0, 0, 0))
    ImageDraw.Draw(ni).text((60, 20), num, font=fn, fill=C["amber"] + (255,))
    ni = glow(ni, 28, 0.6)
    sc = 0.6 + 0.4 * p
    ni2 = ni.resize((max(1, int(ni.width * sc)), max(1, int(ni.height * sc))), Image.BILINEAR)
    if t < 0.6:
        ni2 = ni2.copy(); ni2.putalpha(ni2.getchannel("A").point(lambda v: int(v * min(1, t / 0.25))))
    img.paste(ni2, (int(W2 / 2 - ni2.width / 2), int(80 + (380 - ni2.height) / 2)), ni2)
    # title wipe
    ti = rich_text(title, 104, "grotesk", 700, "white", maxw=1600)
    wp = ease_out((t - 0.35) / 0.5)
    if wp > 0:
        cw = max(1, int(ti.width * wp))
        img.paste(ti.crop((0, 0, cw, ti.height)), (int(W2 / 2 - ti.width / 2), 455), ti.crop((0, 0, cw, ti.height)))
    # amber sweep line
    lp = ease_out((t - 0.2) / 0.6)
    lw = int(900 * lp)
    d.rectangle((W2 / 2 - lw / 2, 440, W2 / 2 + lw / 2, 446), fill=C["amber"] + (255,))
    # progress dots
    for k in range(7):
        a = ease_out((t - 0.6 - k * 0.05) / 0.25)
        if a <= 0:
            continue
        cx = W2 / 2 + (k - 3) * 46
        col = C["amber"] if k + 1 == i else (C["soft"] if k + 1 < i else C["slate"])
        r = 11 if k + 1 == i else 7
        d.ellipse((cx - r, 600 - r, cx + r, 600 + r), fill=col + (int(255 * a),))
    return img


def donut_sprite(e, prog=1.0, now=None):
    v, col = e["value"], C[e.get("color", "amber")]
    R, th = 210, 52
    S = 2
    img = Image.new("RGBA", ((2 * R + 40) * S, (2 * R + 40) * S), (0, 0, 0, 0))  # ring canvas
    d = ImageDraw.Draw(img)
    box = (20 * S, 20 * S, (20 + 2 * R) * S, (20 + 2 * R) * S)
    d.ellipse(box, outline=C["panel"] + (255,), width=th * S)
    p = ease_out(prog)
    if v * p > 0.2:
        d.arc(box, -90, -90 + 360 * v / 100 * p, fill=col + (255,), width=th * S)
    img = img.resize((2 * R + 40, 2 * R + 40), Image.LANCZOS)
    img = glow(img, 16, 0.35)
    dd = ImageDraw.Draw(img)
    fn = font("mono", 104, 800)
    s = e.get("fmt", "{:.0f}%").format(v * p)
    dd.text((img.width / 2 - text_w(fn, s) / 2, img.height / 2 - 66), s, font=fn, fill=col + (255,))
    fl = font("grotesk", 46, 500)
    lab = e.get("label", "")
    out = Image.new("RGBA", (max(img.width, int(text_w(fl, lab)) + 20), img.height + 70), (0, 0, 0, 0))
    out.paste(img, ((out.width - img.width) // 2, 0), img)
    ImageDraw.Draw(out).text((out.width / 2 - text_w(fl, lab) / 2, img.height + 4), lab, font=fl, fill=C["soft"] + (255,))
    return out


def versus_sprite(e, prog=1.0, now=None):
    W2 = 1560
    img = Image.new("RGBA", (W2, 330), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = ease_out(prog)
    for side, (lab, fmt, to, col, frm) in enumerate([e["left"], e["right"]]):
        cx = W2 * (0.24 if side == 0 else 0.76)
        x0 = cx - 330
        d.rounded_rectangle((x0, 20, x0 + 660, 310), radius=22, fill=C["panel"] + (235,),
                            outline=C[col] + (255,), width=3)
        fl = font("mono", 40, 800)
        spaced(d, (cx - spaced_w(fl, lab.upper(), 6) / 2, 50), lab.upper(), fl, C["muted"] + (255,))
        if fmt not in ("", "{}"):
            v = frm + (to - frm) * p
            s = fmt.format(v)
            fv = font("mono", 116 if len(s) <= 9 else 92, 800)
            d.text((cx - text_w(fv, s) / 2, 120 if len(s) <= 9 else 132), s, font=fv, fill=C[col] + (255,))
        if e.get("notes"):
            fn = font("grotesk", 38, 500)
            n = e["notes"][side]
            d.text((cx - text_w(fn, n) / 2, 250), n, font=fn, fill=C["soft"] + (255,))
    d.ellipse((W2 / 2 - 60, 105, W2 / 2 + 60, 225), fill=C["amber"] + (255,))
    fvs = font("grotesk", 56, 700)
    d.text((W2 / 2 - text_w(fvs, "VS") / 2, 130), "VS", font=fvs, fill=(20, 18, 14, 255))
    return img


def timeline_sprite(e, prog=1.0, now=None):
    items = e["items"]
    W2, H2 = 1640, 300
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = len(items)
    p = ease_out(prog) if prog < 1 else 1.0
    x0, x1, y = 70, W2 - 70, 150
    d.line((x0, y, x0 + (x1 - x0) * min(1, p * 1.1), y), fill=C["line"] + (255,), width=6)
    fy = font("mono", 44, 800)
    fl = font("grotesk", 34, 500)
    for k, (year, lab, col) in enumerate(items):
        a = ease_out((p * n - k) / 1.0)
        if a <= 0:
            continue
        cx = x0 + (x1 - x0) * (k / max(1, n - 1))
        r = 14 + 6 * (1 - a)
        d.ellipse((cx - r, y - r, cx + r, y + r), fill=C[col] + (int(255 * a),))
        ys = str(year)
        d.text((cx - text_w(fy, ys) / 2, y - 92 + 10 * (1 - a)), ys, font=fy, fill=C[col] + (int(255 * a),))
        for li, line in enumerate(lab.split("\n")):
            d.text((cx - text_w(fl, line) / 2, y + 36 + li * 40), line, font=fl, fill=C["soft"] + (int(255 * a),))
    return img


def ticker_sprite(e, prog=1.0, now=None):
    t = 0 if now is None else now.get("t", 0)
    W2, H2 = 1920, 96
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 8, W2, H2 - 8), fill=C["panel"] + (240,))
    d.rectangle((0, 8, W2, 11), fill=C["amber"] + (255,))
    f = font("mono", 40, 800)
    items = e["items"]
    widths = [text_w(f, s) + 110 for s, _ in items]
    total = sum(widths)
    off = -(t * 170) % total
    x = off - total
    while x < W2:
        for (s, col), w_ in zip(items, widths):
            if x + w_ > 0 and x < W2:
                d.text((x, 26), s, font=f, fill=C[col] + (255,))
                d.ellipse((x + w_ - 62, 44, x + w_ - 50, 56), fill=C["slate"] + (255,))
            x += w_
    return img


def subscribe_sprite(e, prog=1.0, now=None):
    t = 99 if now is None else now.get("t", 99)
    W2, H2 = 760, 240
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    clicked = t > 1.1
    press = 1 - 0.06 * max(0, 1 - abs(t - 1.1) / 0.12)
    bw, bh = 560 * press, 120 * press
    x0, y0 = W2 / 2 - bw / 2, 60 - (bh - 120) / 2
    col = C["slate"] if clicked else C["amber"]
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=60, fill=col + (255,))
    f = font("grotesk", 56, 700)
    txt = "SUBSCRIBED" if clicked else "SUBSCRIBE"
    tc = C["white"] if clicked else (20, 18, 14)
    tw = text_w(f, txt)
    d.text((W2 / 2 - tw / 2 + 30, y0 + bh / 2 - 38), txt, font=f, fill=tc + (255,))
    # bell icon
    bx, by = W2 / 2 - tw / 2 - 36, y0 + bh / 2
    ang = math.sin(t * 22) * 0.35 * max(0, 1 - abs(t - 1.5) / 0.6) if clicked else 0
    pts = [(-18, 14), (-14, -6), (-8, -16), (0, -19), (8, -16), (14, -6), (18, 14)]
    rot = [(bx + px * math.cos(ang) - py * math.sin(ang), by + px * math.sin(ang) + py * math.cos(ang)) for px, py in pts]
    d.polygon(rot, fill=tc + (255,))
    d.ellipse((bx - 6, by + 14, bx + 6, by + 24), fill=tc + (255,))
    # cursor
    if t < 1.6:
        cp = ease_in_out(t / 1.0)
        cx = W2 - 40 - (W2 - 40 - (W2 / 2 + 120)) * cp
        cy = H2 - 10 - (H2 - 10 - (y0 + bh / 2 + 10)) * cp
        arrow = [(cx, cy), (cx, cy + 46), (cx + 12, cy + 34), (cx + 22, cy + 56), (cx + 30, cy + 52),
                 (cx + 20, cy + 31), (cx + 36, cy + 31)]
        d.polygon(arrow, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    return img


def pause_sprite(e, prog=1.0, now=None):
    t = 99 if now is None else now.get("t", 99)
    txt = e.get("text", "PAUSE & GUESS")
    f = font("mono", 46, 800)
    tw = text_w(f, txt)
    W2, H2 = int(tw + 170), 110
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pulse = 0.5 + 0.5 * math.sin(t * 6)
    d.rounded_rectangle((2, 2, W2 - 2, H2 - 2), radius=55, outline=C["amber"] + (int(160 + 95 * pulse),), width=4,
                        fill=C["panel"] + (230,))
    d.rectangle((48, 32, 60, 78), fill=C["amber"] + (255,))
    d.rectangle((72, 32, 84, 78), fill=C["amber"] + (255,))
    d.text((116, 26), txt, font=f, fill=C["amber"] + (255,))
    return img


def timer_sprite(e, prog=1.0, now=None):
    t = 0 if now is None else now.get("t", 0)
    n = e.get("seconds", 3)
    R = 120
    img = Image.new("RGBA", (2 * R + 40, 2 * R + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = (20, 20, 20 + 2 * R, 20 + 2 * R)
    d.ellipse(box, outline=C["line"] + (255,), width=16)
    rem = max(0.0, n - t)
    num = max(1, math.ceil(rem)) if rem > 0 else 0
    col = C["amber"] if rem > 1 else C["red"]
    d.arc(box, -90, -90 + 360 * (rem / n), fill=col + (255,), width=16)
    fn = font("mono", 130, 800)
    s = str(num) if num else "!"
    d.text((img.width / 2 - text_w(fn, s) / 2, img.height / 2 - 92), s, font=fn, fill=col + (255,))
    return glow(img, 12, 0.3)


def stamp_sprite(e, prog=1.0, now=None):
    txt = e["text"]
    col = C[e.get("color", "red")]
    f = font("grotesk", e.get("size", 84), 700)
    tw = text_w(f, txt)
    pad = 36
    base = Image.new("RGBA", (int(tw + 2 * pad), 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle((4, 4, base.width - 4, 146), radius=14, outline=col + (255,), width=8)
    d.text((pad, 24), txt, font=f, fill=col + (255,))
    return base.rotate(e.get("angle", 8), resample=Image.BICUBIC, expand=True)


def strike_sprite(e, prog=1.0, now=None):
    img = rich_text(e["text"], e.get("size", 170), "mono", 800, "white", maxw=1800)
    pad = 30
    out = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    out.paste(img, (pad, pad), img)
    p = ease_out(prog)
    if p > 0:
        d = ImageDraw.Draw(out)
        y = out.height * 0.55
        d.line((pad - 10, y + 6, pad - 10 + (img.width + 20) * p, y - 10), fill=C["red"] + (255,), width=14)
    return out


EXTRA_KINDS = {
    "chapter_card": chapter_card_sprite, "donut": donut_sprite, "versus": versus_sprite,
    "timeline": timeline_sprite, "ticker": ticker_sprite, "subscribe": subscribe_sprite,
    "pause": pause_sprite, "timer": timer_sprite, "stamp": stamp_sprite, "strike2": strike_sprite,
}

# kinds whose sprite depends on time since appearance (re-rendered while animating)
TIMED = {"chapter_card": 1.4, "ticker": 1e9, "subscribe": 2.4, "pause": 1e9, "timer": 60}
PROG = {"donut": 1.1, "versus": 1.0, "timeline": 1.4, "chips": 0.6, "strike2": 0.35}


# ------------------------------------------------------------------ moving background
@lru_cache(maxsize=1)
def _bg_parts():
    import numpy as np
    base = np.asarray(background_nogrid(), np.float32)
    return base


@lru_cache(maxsize=1)
def background_nogrid():
    import numpy as np
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.zeros((H, W, 3), np.float32)
    base[:] = C["bg"]
    d1 = np.sqrt(((xx - 380) / 1500) ** 2 + ((yy - 120) / 900) ** 2)
    base += (np.clip(1 - d1, 0, 1) ** 2)[..., None] * np.array([6, 12, 22], np.float32)
    d2 = np.sqrt(((xx - 1880) / 700) ** 2 + ((yy - 1060) / 500) ** 2)
    base += (np.clip(1 - d2, 0, 1) ** 2)[..., None] * np.array([14, 4, 2], np.float32)
    dv = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.8)) ** 2)
    base *= (1 - 0.35 * np.clip(dv - 0.35, 0, 1))[..., None]
    return Image.fromarray(np.clip(base, 0, 255).astype("uint8"), "RGB")


_BG_CACHE = {}


def background_at(t):
    """Grid drifting diagonally (period 80px), cached per offset."""
    import numpy as np
    off = int(t * 14) % 80
    img = _BG_CACHE.get(off)
    if img is None:
        base = _bg_parts().copy()
        grid = np.zeros((H, W), np.float32)
        grid[:, (np.arange(W) + off) % 80 == 0] = 1
        grid[(np.arange(H) + off) % 80 == 0, :] = 1
        base += grid[..., None] * np.array([4, 6, 9], np.float32)
        img = Image.fromarray(np.clip(base, 0, 255).astype("uint8"), "RGB")
        _BG_CACHE[off] = img
    return img


def _particles():
    import random
    rnd = random.Random(42)
    return [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(8, 26), rnd.choice([2, 2, 3, 3, 4]),
             rnd.uniform(0, 6.28), rnd.random() < 0.18) for _ in range(42)]


PARTICLES = _particles()


def draw_particles(frame, t):
    d = ImageDraw.Draw(frame)
    for x0, y0, sp, r, ph, warm in PARTICLES:
        y = (y0 - sp * t) % (H + 40) - 20
        x = x0 + 18 * math.sin(t * 0.25 + ph)
        tw = 0.6 + 0.4 * math.sin(t * 1.3 + ph * 3)
        col = (int(70 * tw), int(56 * tw), int(26 * tw)) if warm else (int(38 * tw), int(50 * tw), int(72 * tw))
        d.ellipse((x - r, y - r, x + r, y + r), fill=col)


@lru_cache(maxsize=16)
def tracker_sprite(text):
    f = font("mono", 26, 700)
    w = int(spaced_w(f, text, 4)) + 10
    img = Image.new("RGBA", (w, 40), (0, 0, 0, 0))
    spaced(ImageDraw.Draw(img), (4, 4), text, f, C["muted"] + (200,), 4)
    return img
