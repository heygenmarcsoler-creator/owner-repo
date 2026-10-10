"""v3/v4 renderer — EuroindexLab long-form format (16:9, no word captions).

  python3 render_v3.py timeline        # align + timeline + audio mix
  python3 render_v3.py render [t0 t1]  # frames -> MP4 (optionally a time range)
  python3 render_v3.py all
"""
import json
import math
import multiprocessing as mp
import os
import random
import re
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import engine as E
import music
from script_v3 import SEGMENTS, CHUNK_STARTS

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build", os.environ.get("BUILD_DIR", "v4"))
TTS = os.path.join(HERE, "build", os.environ.get("TTS_DIR", "tts_v4"))
OUT = os.path.join(HERE, "output")
SR = 24000
W, H, FPS = 1920, 1080, 30
TARGET = float(os.environ.get("TARGET_SECONDS", 1800))
PART_CRF = int(os.environ.get("PART_CRF", 12))  # near-lossless 4:4:4 intermediate; exports re-encode
TEMPO = float(os.environ.get("TEMPO", 1.0))  # 1.0 = natural speed (time-stretching made the voice robotic)
TTS_SLOW = os.path.join(HERE, "build", "tts_v3_slow")


INSTRUCTION_WORDS = {"script", "narrator", "documentary", "investors", "presenter", "finance", "instruction"}


def reads_instruction(path, seconds=25):
    """True if the TTS model read its style instruction aloud at the start of this chunk."""
    from pocketsphinx import Decoder
    from sphinx_align import pcm16k
    pcm = pcm16k(path)[: seconds * 16000 * 2]
    d = Decoder(samprate=16000, loglevel="FATAL")
    d.start_utt(); d.process_raw(pcm, full_utt=True); d.end_utt()
    heard = set(d.hyp().hypstr.split()) if d.hyp() else set()
    return len(heard & INSTRUCTION_WORDS) >= 2


def clean_path(path, ids):
    """Cut the spoken style instruction (if any) from the start of a TTS chunk."""
    from sphinx_align import align
    import tts_v3
    out_dir = TTS + "_clean"
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, os.path.basename(path))
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(path):
        return dst
    a = read_wav(path)
    cut = 0.0
    if reads_instruction(path):
        instr = tts_v3.T.STYLE.split()
        toks = instr + [w for si in ids for w in spoken(SEGMENTS[si]["text"]).split()]
        times = align(path, toks)
        t_end, t_first = times[len(instr) - 1][1], times[len(instr)][0]
        # cut in the quietest 20 ms just before the first script word
        fr = int(0.02 * SR)
        lo, hi = int(t_end * SR), max(int(t_end * SR) + fr, int(t_first * SR) - fr)
        best = min(range(lo, hi, fr), key=lambda i: float((a[i:i + fr] ** 2).mean()))
        cut = best / SR
        print(f"  {os.path.basename(path)}: spoken instruction removed (first {cut:.1f}s)")
    with wave.open(dst, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(a[int(cut * SR):], -1, 1) * 32767).astype("<i2").tobytes())
    return dst


def tight_path(path, max_sil=1.2, keep=0.9, floor_db=-45):
    """Natural-speed voice: only shorten silent stretches longer than max_sil seconds to keep seconds."""
    out_dir = TTS + "_tight"
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, os.path.basename(path))
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(path):
        return dst
    a = read_wav(path)
    fr = int(0.02 * SR)
    n = len(a) // fr
    db = 20 * np.log10(np.sqrt((a[:n * fr].reshape(n, fr) ** 2).mean(1)) + 1e-9)
    pieces, last, i = [], 0, 0
    while i < n:
        if db[i] < floor_db:
            j = i
            while j < n and db[j] < floor_db:
                j += 1
            if (j - i) * 0.02 > max_sil:
                half = int(keep / 2 * SR)
                a0, a1 = i * fr + half, j * fr - half
                pieces.append(a[last:a0])
                last = a1
            i = j
        else:
            i += 1
    pieces.append(a[last:])
    y = np.concatenate(pieces)
    with wave.open(dst, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return dst


def slow_path(path):
    if abs(TEMPO - 1.0) < 1e-6:
        return tight_path(path)
    os.makedirs(TTS_SLOW, exist_ok=True)
    dst = os.path.join(TTS_SLOW, os.path.basename(path).replace(".wav", f"_{TEMPO:.3f}.wav"))
    if not os.path.exists(dst):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-af", f"atempo={TEMPO}", "-ar", "24000", "-ac", "1", dst],
                       check=True)
    return dst

# ------------------------------------------------------------------ palette (channel long-form)
E.C.update({
    "bg": (11, 14, 20), "amber": (245, 158, 11), "green": (34, 197, 94), "red": (248, 113, 113),
    "blue": (59, 130, 246), "cyan": (56, 189, 248), "purple": (167, 139, 250), "white": (248, 250, 252),
    "muted": (148, 163, 184), "soft": (203, 213, 225), "slate": (100, 116, 139), "panel": (24, 28, 37),
    "line": (44, 51, 64), "source": (100, 112, 135),
})
C = E.C
KX, KY, TY = 80, 62, 100
CANVAS = (80, 232, 1840, 905)
NOTE_Y, SRC_Y = 912, 1012


def font(f, s, w=700):
    return E.font(f, s, w)


def tw(f, s):
    return f.getlength(s)


def ease(x):
    return E.ease_out(x)


def eio(x):
    return E.ease_in_out(x)


def back(x):
    return E.ease_out_back(x, 1.4)


# ------------------------------------------------------------------ background (clean, radial glow)
SSAA = 4
_AA_CACHE = {}


def _aa_shape(orig, draw, xy, kw):
    """Draw a shape 4x supersampled and composite it, so edges are anti-aliased."""
    img = getattr(draw, "_image", None)
    if img is None or img.mode != "RGBA":
        return orig(draw, xy, **kw)
    (x0, y0), (x1, y1) = xy if len(xy) == 2 else ((xy[0], xy[1]), (xy[2], xy[3]))
    if x1 < x0 or y1 < y0:
        return orig(draw, xy, **kw)
    bx0, by0 = int(math.floor(x0)) - 1, int(math.floor(y0)) - 1
    bw, bh = int(math.ceil(x1)) + 2 - bx0, int(math.ceil(y1)) + 2 - by0
    key = (orig.__name__, bw, bh, round(x0 - bx0, 2), round(y0 - by0, 2), round(x1 - bx0, 2), round(y1 - by0, 2),
           tuple(sorted((k, v if not isinstance(v, list) else tuple(v)) for k, v in kw.items())))
    small = _AA_CACHE.get(key)
    if small is None:
        layer = Image.new("RGBA", (bw * SSAA, bh * SSAA), (0, 0, 0, 0))
        kw2 = dict(kw)
        if kw2.get("radius"):
            kw2["radius"] = kw2["radius"] * SSAA
        if kw2.get("width"):
            kw2["width"] = int(round(kw2["width"] * SSAA))
        box = ((x0 - bx0) * SSAA, (y0 - by0) * SSAA, (x1 - bx0 + 1) * SSAA - 1, (y1 - by0 + 1) * SSAA - 1)
        orig(ImageDraw.Draw(layer), box, **kw2)
        small = layer.resize((bw, bh), Image.BOX)
        if len(_AA_CACHE) > 150:
            _AA_CACHE.clear()
        _AA_CACHE[key] = small
    if bx0 < 0 or by0 < 0:
        small = small.crop((max(0, -bx0), max(0, -by0), bw, bh))
        bx0, by0 = max(0, bx0), max(0, by0)
    if bx0 >= img.width or by0 >= img.height:
        return
    small = small.crop((0, 0, min(small.width, img.width - bx0), min(small.height, img.height - by0)))
    img.alpha_composite(small, (bx0, by0))


_RRECT, _ELLIPSE = ImageDraw.ImageDraw.rounded_rectangle, ImageDraw.ImageDraw.ellipse
ImageDraw.ImageDraw.rounded_rectangle = lambda self, xy, **kw: _aa_shape(_RRECT, self, xy, kw)
ImageDraw.ImageDraw.ellipse = lambda self, xy, **kw: _aa_shape(_ELLIPSE, self, xy, kw)

_BG = None


def background():
    global _BG
    if _BG is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        base = np.zeros((H, W, 3), np.float32)
        top = np.array([11, 14, 20], np.float32)
        bot = np.array([7, 10, 15], np.float32)
        t = (yy / H)[..., None]
        base[:] = top * (1 - t) + bot * t
        d = np.sqrt(((xx - W * 0.55) / (W * 0.55)) ** 2 + ((yy - H * 0.52) / (H * 0.62)) ** 2)
        base += (np.clip(1 - d, 0, 1) ** 2)[..., None] * np.array([10, 16, 28], np.float32)
        dv = np.sqrt(((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - H / 2) / (H * 0.75)) ** 2)
        base *= (1 - 0.3 * np.clip(dv - 0.45, 0, 1))[..., None]
        base += np.random.default_rng(7).uniform(-0.5, 0.5, base.shape).astype(np.float32)
        _BG = Image.fromarray(np.clip(np.round(base), 0, 255).astype("uint8"), "RGB")
    return _BG


# ------------------------------------------------------------------ helpers
def glass(d, box, r=20, accent=None, alpha=235, border=None):
    d.rounded_rectangle(box, radius=r, fill=C["panel"] + (alpha,), outline=(border or C["line"]) + (255,), width=2)
    if accent:
        x0, y0, x1, _ = box
        d.rounded_rectangle((x0 + 18, y0, x1 - 18, y0 + 5), radius=3, fill=C[accent] + (255,))


def spaced(d, xy, text, f, fill, sp=5):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += tw(f, ch) + sp
    return x


def spaced_w(f, text, sp=5):
    return sum(tw(f, ch) + sp for ch in text) - sp


def money(v):
    a = abs(v)
    s = "−" if v < 0 else ""
    if a >= 100000:
        return f"{s}€{a / 1000:.0f}k"
    if a >= 10000:
        return f"{s}€{a / 1000:.1f}k".replace(".0k", "k")
    if a >= 1000:
        return f"{s}€{a / 1000:.1f}k"
    return f"{s}€{a:.0f}"


def alpha_img(img, a):
    if a >= 0.999:
        return img
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return img


_SC_CACHE = {}


def scaled(img, s):
    if abs(s - 1) < 0.004:
        return img
    key = (id(img), round(s, 4))
    hit = _SC_CACHE.get(key)
    if hit is not None and hit[0] is img:
        return hit[1]
    out = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    if len(_SC_CACHE) > 40:
        _SC_CACHE.clear()
    _SC_CACHE[key] = (img, out)
    return out


def glow_text(text, f, col, radius=22, strength=0.55):
    pad = 40
    w_, h_ = int(tw(f, text)) + 2 * pad, int(f.size * 1.35) + 2 * pad
    img = Image.new("RGBA", (w_, h_), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad, pad), text, font=f, fill=col + (255,))
    return E.glow(img, radius, strength)


def wrap(text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if cur and tw(f, t) > maxw:
            lines.append(cur); cur = wd
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ element sprites
def sp_statement(e, p=1.0, now=None):
    f = font("grotesk", e.get("size", 72), 700)
    lines = wrap(e["text"], f, 1560)
    lh = int(f.size * 1.18)
    img = Image.new("RGBA", (1600, lh * len(lines) + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((0, i * lh), ln, font=f, fill=C["white"] + (255,))
    return img


def sp_note(e, p=1.0, now=None):
    f = font("inter", 30, 500)
    w_ = int(tw(f, e["text"])) + 84
    img = Image.new("RGBA", (w_, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    glass(d, (0, 0, w_ - 1, 63), r=32)
    d.ellipse((26, 26, 38, 38), fill=C["amber"] + (255,))
    d.text((54, 14), e["text"], font=f, fill=C["soft"] + (255,))
    return img


def sp_cnt(e, p=1.0, now=None):
    v = e.get("frm", 0) + (e["to"] - e.get("frm", 0)) * p
    fmt = e["fmt"]
    s = fmt.format(abs(v) if fmt.startswith("−") else v).replace("-", "−")
    f = font("mono", e.get("size", 210), 800)
    g = glow_text(s, f, C[e.get("color", "amber")])
    lab = e.get("label")
    if not lab:
        return g
    fl = font("inter", 32, 500)
    lines = wrap(lab, fl, 1500)
    w_ = max(g.width, int(max(tw(fl, l) for l in lines)) + 20)
    img = Image.new("RGBA", (w_, g.height + 46 * len(lines) - 10), (0, 0, 0, 0))
    img.paste(g, ((w_ - g.width) // 2, 0), g)
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text(((w_ - tw(fl, l)) / 2, g.height - 40 + i * 46), l, font=fl, fill=C["muted"] + (255,))
    return img


def sp_cards(e, p=1.0, now=None):
    items = e["items"]
    n = len(items)
    cw = 600 if n <= 2 else (520 if n == 3 else 400)
    gap = 40
    ch = 330
    W2 = n * cw + (n - 1) * gap
    img = Image.new("RGBA", (W2, ch + 40), (0, 0, 0, 0))
    fk = font("inter", 28, 600)
    fv = font("mono", 112 if n <= 3 else 86, 800)
    fs = font("inter", 32, 500)
    for i, (kick, val, sub, col) in enumerate(items):
        a = ease((p * (n + 0.6) - i * 0.6) / 1.0) if p < 1 else 1.0
        if a <= 0:
            continue
        card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        glass(d, (0, 0, cw - 1, ch - 1), r=24, accent=col if col not in ("white",) else None)
        spaced(d, (40, 44), kick.upper(), fk, C["muted"] + (255,), 2)
        vf = fv
        while tw(vf, val) > cw - 60 and vf.size > 40:
            vf = font("mono", vf.size - 6, 800)
        d.text((40, 100), val, font=vf, fill=C.get(col, C["white"]) + (255,))
        for li, l in enumerate(wrap(sub, fs, cw - 76)[:2]):
            d.text((40, 244 + li * 40), l, font=fs, fill=C["soft"] + (255,))
        card = alpha_img(card, a)
        img.alpha_composite(card, (i * (cw + gap), int(20 + 20 * (1 - a))))
    return img


def sp_rows(e, p=1.0, now=None):
    items = e["items"]
    width = 1300
    rh = 100
    img = Image.new("RGBA", (width, rh * len(items)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fk = font("inter", 38, 500)
    fv = font("mono", 44, 800)
    for i, (k, v, col) in enumerate(items):
        y = i * rh
        glass(d, (0, y + 8, width - 1, y + rh - 8), r=18)
        if len(k) <= 2:
            d.text((34, y + 26), k, font=fv, fill=C["muted"] + (255,))
            d.text((100, y + 28), v, font=fk, fill=C.get(col, C["white"]) + (255,))
            continue
        d.text((34, y + 28), k, font=fk, fill=C["soft"] + (255,))
        if v == "✓":
            E.draw_check(d, width - 80, y + 32, 38, C[col] + (255,), 7)
        else:
            d.text((width - 34 - tw(fv, v), y + 25), v, font=fv, fill=C.get(col, C["white"]) + (255,))
    return img


def sp_bars(e, p=1.0, now=None):
    items = e["items"]
    width, lab_w, rh = 1560, 600, 88
    bar_w = width - lab_w - 250
    maxv = e.get("maxv") or max(v for _, v, _, _ in items) * 1.1
    img = Image.new("RGBA", (width, rh * len(items)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fl = font("inter", 36, 500)
    fv = font("mono", 42, 800)
    pp = ease(p)
    for i, (lab, v, disp, col) in enumerate(items):
        y = i * rh
        d.text((lab_w - 28 - tw(fl, lab), y + 22), lab, font=fl, fill=C["soft"] + (255,))
        d.rounded_rectangle((lab_w, y + 22, lab_w + bar_w, y + rh - 22), radius=22, fill=C["panel"] + (255,))
        bw = max(10, bar_w * min(1, v / maxv) * pp)
        d.rounded_rectangle((lab_w, y + 22, lab_w + bw, y + rh - 22), radius=22, fill=C[col] + (255,))
        if pp > 0.35:
            a = int(255 * min(1, (pp - 0.35) / 0.4))
            d.text((lab_w + bw + 22, y + 18), disp, font=fv, fill=C[col if col != "slate" else "muted"] + (a,))
    return img


def sp_vbars(e, p=1.0, now=None):
    items = e["items"]
    n = len(items)
    bw = 96 if n > 6 else 150
    gap = 44 if n > 6 else 80
    H2 = 520
    W2 = n * bw + (n - 1) * gap
    img = Image.new("RGBA", (max(W2, 400), H2 + 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    maxv = e.get("maxv") or max(v for _, v, _, _ in items) * 1.15
    fl = font("mono", 30, 700)
    fv = font("mono", 36, 800)
    x0 = (img.width - W2) / 2
    d.line((x0 - 20, H2, x0 + W2 + 20, H2), fill=C["line"] + (255,), width=2)
    vis = e.get("_vis")
    for i, (lab, v, disp, col) in enumerate(items):
        q = ease(p * n - i * 0.7) if p < 1 else 1.0
        if vis is not None:
            q = ease(vis[i])
        q = max(0.0, min(1.0, q))
        x = x0 + i * (bw + gap)
        bh = (H2 - 70) * v / maxv * q
        if bh > 1:
            d.rounded_rectangle((x, H2 - bh, x + bw, H2), radius=12, fill=C[col] + (255,))
            d.rectangle((x, H2 - min(bh, 12), x + bw, H2), fill=C[col] + (255,))
        if q > 0.5:
            a = int(255 * min(1, (q - 0.5) / 0.4))
            d.text((x + bw / 2 - tw(fv, disp) / 2, H2 - bh - 52), disp, font=fv, fill=C[col] + (a,))
        d.text((x + bw / 2 - tw(fl, lab) / 2, H2 + 18), lab, font=fl, fill=C["muted"] + (255,))
    return img


def heat_color(v):
    if v is None:
        return (20, 24, 32)
    if v < 0:
        t = min(1, -v / 45)
        a, b = np.array([60, 40, 48]), np.array(C["red"])
    else:
        t = min(1, v / 150)
        a, b = np.array([30, 52, 44]), np.array(C["green"])
    c = a + (b - a) * (0.25 + 0.75 * t)
    return tuple(int(x) for x in c)


def sp_heat(e, p=1.0, now=None):
    rows, cols, vals = e["rowl"], e["coll"], e["values"]
    nr, nc = len(rows), len(cols)
    cw, chh, lw, top = 116, 34, 130, 50
    img = Image.new("RGBA", (lw + nc * cw + 10, top + nr * chh + 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fr = font("mono", 22, 700)
    fc = font("inter", 19, 600)
    for j, c in enumerate(cols):
        s = f"{c}y"
        d.text((lw + j * cw + cw / 2 - tw(fr, s) / 2, 10), s, font=fr, fill=C["muted"] + (255,))
    hl = e.get("hl")
    hp = e.get("_hp", 1.0)
    sel = None
    if hl:
        sel = set()
        if hl == "neg":
            sel = {(i, j) for i in range(nr) for j in range(nc) if vals[i][j] is not None and vals[i][j] < 0}
        elif hl.startswith("rows:"):
            for part in hl[5:].split(","):
                a_, b_ = (part.split("-") + [part])[:2]
                for i in range(int(a_), int(b_) + 1):
                    sel |= {(i, j) for j in range(nc)}
        elif hl.startswith("col:"):
            jj = int(hl[4:])
            sel = {(i, jj) for i in range(nr)}
    reveal = e.get("reveal")
    for i, r in enumerate(rows):
        ra = 1.0 if reveal != "rows" or p >= 1 else max(0.0, min(1.0, p * nr * 1.05 - i))
        d.text((lw - 20 - tw(fr, r), top + i * chh + 6), r, font=fr, fill=C["muted"] + (255,))
        for j in range(nc):
            v = vals[i][j]
            x, y = lw + j * cw, top + i * chh
            col = heat_color(v)
            dim = sel is not None and (i, j) not in sel
            a = int(255 * ra * (1 - 0.65 * hp if dim else 1))
            d.rectangle((x + 2, y + 2, x + cw - 2, y + chh - 2), fill=col + (a,))
            if v is not None and ra > 0.5:
                s = f"{v:+.0f}%"
                tc = (255, 255, 255, int(a * 0.95))
                d.text((x + cw / 2 - tw(fc, s) / 2, y + 7), s, font=fc, fill=tc)
    if sel and hp > 0:
        for (i, j) in sel:
            x, y = lw + j * cw, top + i * chh
            d.rectangle((x + 1, y + 1, x + cw - 1, y + chh - 1), outline=(255, 255, 255, int(200 * hp)), width=2)
    return img


_DOT_ORDER = None


def sp_dots(e, p=1.0, now=None):
    global _DOT_ORDER
    n, s, gp = 100, 6, 2
    size = n * (s + gp)
    lab = e.get("label")
    img = Image.new("RGBA", (max(size, 1000), size + (70 if lab else 0)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if _DOT_ORDER is None:
        idx = list(range(n * n))
        random.Random(7).shuffle(idx)
        _DOT_ORDER = {k: r for r, k in enumerate(idx)}
    red_n = int(e.get("red", 0) / 100 * n * n * min(1.0, e.get("_rp", 1.0)))
    x0 = (img.width - size) / 2
    fillp = min(1.0, p * 1.0)
    for k in range(n * n):
        r, c = divmod(k, n)
        if k / (n * n) > fillp:
            break
        col = C[e.get("color", "red")] if _DOT_ORDER[k] < red_n else (58, 66, 82)
        x, y = x0 + c * (s + gp), r * (s + gp)
        d.rectangle((x, y, x + s - 1, y + s - 1), fill=col + (255,))
    if lab:
        fl = font("inter", 32, 500)
        d.text((img.width / 2 - tw(fl, lab) / 2, size + 22), lab, font=fl, fill=C["muted"] + (255,))
    return img


def fmt_axis(v, e):
    if e.get("money"):
        return money(v)
    if e.get("dec"):
        return f"${v:.{e['dec']}f}"
    if v >= 1000:
        return f"{v / 1000:.1f}k"
    return f"{v:.0f}"


def sp_line(e, p=1.0, now=None):
    S = 2
    w2, h2 = 1640, 600
    pad_l, pad_r, pad_t, pad_b = 130, 290, 40, 70
    img = Image.new("RGBA", (w2 * S, h2 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, x1 = e["xr"]
    y0, y1 = e["yr"]
    pw, ph = (w2 - pad_l - pad_r) * S, (h2 - pad_t - pad_b) * S

    def X(x):
        return pad_l * S + (x - x0) / (x1 - x0) * pw

    def Y(y):
        return pad_t * S + ph - (min(max(y, y0), y1) - y0) / (y1 - y0) * ph

    fy = font("mono", 24 * S, 600)
    for val, lab in e.get("yticks", []):
        yy = Y(val)
        d.line((pad_l * S, yy, pad_l * S + pw, yy), fill=C["line"] + (150,), width=S)
        d.text((pad_l * S - 18 * S - tw(fy, lab), yy - 16 * S), lab, font=fy, fill=C["muted"] + (255,))
    for xt in e.get("xticks", []):
        lab = f"{xt}y" if e.get("xlabel") == "years" else str(xt)
        d.text((X(xt) - tw(fy, lab) / 2, pad_t * S + ph + 22 * S), lab, font=fy, fill=C["muted"] + (255,))
    if e.get("ref") is not None:
        yy = Y(e["ref"])
        xx = pad_l * S
        while xx < pad_l * S + pw:
            d.line((xx, yy, min(xx + 16 * S, pad_l * S + pw), yy), fill=C["slate"] + (255,), width=2 * S)
            xx += 28 * S
    pr = eio(p) if p < 1 else 1.0

    def clip_pts(xs, ys, lim):
        pts = []
        for i, (x, y) in enumerate(zip(xs, ys)):
            if x <= lim + 1e-9:
                pts.append((x, y))
            else:
                if i > 0 and xs[i - 1] < lim:
                    f = (lim - xs[i - 1]) / (x - xs[i - 1])
                    pts.append((lim, ys[i - 1] + (y - ys[i - 1]) * f))
                break
        return pts
    # bands (fan chart)
    first = e["series"][0]
    lim_band = first["x"][0] + (first.get("upto", first["x"][-1]) - first["x"][0]) * pr
    for key, alpha in (("band", 46), ("band2", 80)):
        if e.get(key):
            lo, hi = e[key]
            xs = first["x"]
            plo = clip_pts(xs, lo, lim_band)
            phi = clip_pts(xs, hi, lim_band)
            if len(plo) >= 2:
                poly = [(X(x), Y(y)) for x, y in phi] + [(X(x), Y(y)) for x, y in reversed(plo)]
                band = Image.new("RGBA", img.size, (0, 0, 0, 0))
                ImageDraw.Draw(band).polygon(poly, fill=C[first["color"]] + (alpha,))
                img = Image.alpha_composite(img, band)
    d = ImageDraw.Draw(img)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    tags = []
    for s_ in e["series"]:
        xs, ys = s_["x"], s_["y"]
        upto = s_.get("upto", xs[-1])
        frm = s_.get("frm")
        if p >= 1:
            lim = upto
        elif frm is not None:
            lim = frm + (upto - frm) * pr
        else:
            lim = xs[0] + (upto - xs[0]) * pr
        pts = clip_pts(xs, ys, lim)
        if len(pts) < 2:
            continue
        col = C[s_.get("color", "amber")]
        sp_ = [(X(x), Y(y)) for x, y in pts]
        ld.line(sp_, fill=col + (255,), width=6 * S, joint="curve")
        ex, ey = sp_[-1]
        r = 11 * S
        ld.ellipse((ex - r, ey - r, ex + r, ey + r), fill=col + (255,))
        ld.ellipse((ex - r / 2.4, ey - r / 2.4, ex + r / 2.4, ey + r / 2.4), fill=(255, 255, 255, 255))
        tags.append((ex, ey, pts[-1][1], col, s_.get("label")))
    gl = layer.getchannel("A").filter(ImageFilter.GaussianBlur(12 * S)).point(lambda v: int(v * 0.55))
    glow_l = Image.new("RGBA", img.size, C[first.get("color", "amber")] + (0,))
    glow_l.putalpha(gl)
    img = Image.alpha_composite(img, glow_l)
    img = Image.alpha_composite(img, layer)
    d = ImageDraw.Draw(img)
    ft = font("mono", 28 * S, 800)
    fl = font("inter", 22 * S, 600)
    tags.sort(key=lambda t: t[1])
    last_y = -1e9
    for ex, ey, val, col, lab in tags:
        txt = fmt_axis(val, e)
        bw_ = tw(ft, txt) + 26 * S
        bx, by = ex + 22 * S, ey - 22 * S
        by = max(by, last_y + 50 * S)
        last_y = by
        d.rounded_rectangle((bx, by, bx + bw_, by + 44 * S), radius=10 * S, fill=col + (235,))
        d.text((bx + 13 * S, by + 5 * S), txt, font=ft, fill=(10, 14, 20, 255))
        if lab:
            d.text((bx + bw_ + 10 * S, by + 10 * S), lab, font=fl, fill=C["soft"] + (255,))
    return img.resize((w2, h2), Image.LANCZOS)


def sp_waffle(e, p=1.0, now=None):
    cols_ = []
    for cnt, col, _ in e["groups"]:
        cols_ += [col] * cnt
    cols_ = (cols_ + ["slate"] * 100)[:100]
    sq, gp = 50, 10
    gw = 10 * sq + 9 * gp
    legend = [(c, l, n) for n, c, l in e["groups"] if l]
    fl = font("inter", 36, 500)
    lw = (70 + max(tw(fl, f"€{n}  {l}") for c, l, n in legend) + 40) if legend else 0
    img = Image.new("RGBA", (int(gw + lw + 60), gw), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pp = ease(p)
    for i in range(100):
        r, c = divmod(i, 10)
        x, y = c * (sq + gp), r * (sq + gp)
        col = cols_[i]
        filled = i < pp * 100.0001
        base = (52, 60, 76) if (not filled or col == "slate") else C[col]
        d.rounded_rectangle((x, y, x + sq, y + sq), radius=8, fill=base + (255,))
    if legend:
        lx = gw + 70
        ly = gw / 2 - len(legend) * 70 / 2
        for i, (col, lab, n) in enumerate(legend):
            y = ly + i * 70
            d.rounded_rectangle((lx, y + 8, lx + 34, y + 42), radius=8, fill=C[col] + (255,))
            d.text((lx + 52, y + 2), f"€{n}  {lab}", font=fl, fill=C["soft"] + (255,))
    return img


def sp_donut(e, p=1.0, now=None):
    v, col = e["value"], C[e.get("color", "amber")]
    R, th, S = 200, 50, 2
    ring = Image.new("RGBA", ((2 * R + 40) * S, (2 * R + 40) * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    box = (20 * S, 20 * S, (20 + 2 * R) * S, (20 + 2 * R) * S)
    d.ellipse(box, outline=C["panel"] + (255,), width=th * S)
    pp = ease(p)
    if v * pp > 0.3:
        d.arc(box, -90, -90 + 360 * v / 100 * pp, fill=col + (255,), width=th * S)
    ring = E.glow(ring.resize((2 * R + 40, 2 * R + 40), Image.LANCZOS), 14, 0.3)
    dd = ImageDraw.Draw(ring)
    fn = font("mono", 100, 800)
    s = f"{v * pp:.0f}%"
    dd.text((ring.width / 2 - tw(fn, s) / 2, ring.height / 2 - 66), s, font=fn, fill=col + (255,))
    fl = font("inter", 34, 500)
    lab = e.get("label", "")
    out = Image.new("RGBA", (max(ring.width, int(tw(fl, lab)) + 20), ring.height + 64), (0, 0, 0, 0))
    out.paste(ring, ((out.width - ring.width) // 2, 0), ring)
    ImageDraw.Draw(out).text((out.width / 2 - tw(fl, lab) / 2, ring.height + 8), lab, font=fl, fill=C["muted"] + (255,))
    return out


def sp_chips(e, p=1.0, now=None):
    f = font("inter", 42, 600)
    items = e["items"]
    ws = [tw(f, t) + 70 for t in items]
    W2 = int(sum(ws) + 22 * (len(items) - 1))
    rows_, cur, cw = [], [], 0
    for t, w_ in zip(items, ws):
        if cur and cw + w_ > 1700:
            rows_.append(cur); cur, cw = [], 0
        cur.append((t, w_)); cw += w_ + 22
    rows_.append(cur)
    W2 = int(max(sum(w_ for _, w_ in r) + 22 * (len(r) - 1) for r in rows_))
    img = Image.new("RGBA", (W2, 104 * len(rows_)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shown = len(items) if p >= 1 else int(p * len(items) + 0.999)
    k = 0
    for ri, r in enumerate(rows_):
        x = (W2 - (sum(w_ for _, w_ in r) + 22 * (len(r) - 1))) / 2
        for t, w_ in r:
            k += 1
            if k > shown:
                break
            glass(d, (x, ri * 104, x + w_, ri * 104 + 84), r=42)
            d.text((x + 35, ri * 104 + 16), t, font=f, fill=C["white"] + (255,))
            x += w_ + 22
    return img


def sp_table(e, p=1.0, now=None):
    header, items = e["header"], e["items"]
    width, rh = 1400, 96
    img = Image.new("RGBA", (width, rh * (len(items) + 1) + 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fh = font("mono", 40, 800)
    fk = font("inter", 38, 500)
    fv = font("mono", 48, 800)
    cx = [0, width * 0.70, width * 0.88]
    for j, h_ in enumerate(header):
        if h_:
            d.text((cx[j] - tw(fh, h_) / 2, 20), h_, font=fh, fill=(C["muted"] if j == 1 else C["amber"]) + (255,))
    d.line((0, rh, width, rh), fill=C["line"] + (255,), width=2)
    for i, (k, a, b) in enumerate(items):
        y = rh * (i + 1)
        glass(d, (0, y + 6, width - 1, y + rh - 6), r=16)
        d.text((30, y + 26), k, font=fk, fill=C["soft"] + (255,))
        d.text((cx[1] - tw(fv, a) / 2, y + 20), a, font=fv, fill=C["muted"] + (255,))
        d.text((cx[2] - tw(fv, b) / 2, y + 20), b, font=fv, fill=C["red"] + (255,))
    return img


def sp_timeline(e, p=1.0, now=None):
    items = e["items"]
    W2, H2 = 1600, 300
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = len(items)
    pp = ease(p) if p < 1 else 1.0
    x0, x1, y = 80, W2 - 80, 140
    d.line((x0, y, x0 + (x1 - x0) * min(1, pp * 1.1), y), fill=C["line"] + (255,), width=6)
    fy = font("mono", 42, 800)
    fl = font("inter", 32, 500)
    for k, (year, lab, col) in enumerate(items):
        a = ease(pp * n - k) if pp < 1 else 1.0
        if a <= 0:
            continue
        cx = x0 + (x1 - x0) * (k / max(1, n - 1))
        r = 14
        d.ellipse((cx - r, y - r, cx + r, y + r), fill=C[col] + (int(255 * a),))
        ys = str(year)
        d.text((cx - tw(fy, ys) / 2, y - 90), ys, font=fy, fill=C[col] + (int(255 * a),))
        for li, line_ in enumerate(lab.split("\n")):
            d.text((cx - tw(fl, line_) / 2, y + 34 + li * 38), line_, font=fl, fill=C["soft"] + (int(255 * a),))
    return img


def sp_takeaways(e, p=1.0, now=None):
    items = e["items"]
    n = len(items)
    cw, gap, ch = 500, 40, 330
    img = Image.new("RGBA", (n * cw + (n - 1) * gap, ch + 30), (0, 0, 0, 0))
    hl = e.get("hl")
    fnum = font("mono", 64, 800)
    ft = font("grotesk", 44, 700)
    for i, txt in enumerate(items):
        a = ease(p * (n + 0.5) - i * 0.6) if p < 1 else 1.0
        if a <= 0:
            continue
        on = hl is None or hl == i
        card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        glass(d, (0, 0, cw - 1, ch - 1), r=26, accent="amber" if hl == i else None,
              border=C["amber"] if hl == i else None)
        d.text((36, 30), f"{i + 1:02d}", font=fnum, fill=(C["amber"] if on else C["muted"]) + (255,))
        for li, l in enumerate(wrap(txt, ft, cw - 70)[:4]):
            d.text((36, 130 + li * 54), l, font=ft, fill=(C["white"] if on else C["muted"]) + (255,))
        card = alpha_img(card, a * (1 if on else 0.7))
        img.alpha_composite(card, (i * (cw + gap), int(15 + 20 * (1 - a))))
    return img


def sp_endcard(e, p=1.0, now=None):
    W2, H2 = 1400, 560
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fl = font("mono", 36, 800)
    spaced(d, (W2 / 2 - spaced_w(fl, e["label"], 8) / 2, 0), e["label"], fl, C["amber"] + (255,), 8)
    glass(d, (0, 70, W2 - 1, 370), r=28, accent="amber")
    ft = font("grotesk", 60, 700)
    lines = wrap(e["title"], ft, W2 - 140)
    for i, l in enumerate(lines[:3]):
        d.text((W2 / 2 - tw(ft, l) / 2, 130 + i * 74), l, font=ft, fill=C["white"] + (255,))
    t = 99 if now is None else now
    pulse = 1 + 0.03 * math.sin(t * 4)
    fb = font("grotesk", 46, 700)
    txt = "SUBSCRIBE"
    bw, bh = (tw(fb, txt) + 90) * pulse, 96 * pulse
    bx, by = W2 / 2 - bw / 2, 430 - (bh - 96) / 2
    d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=48, fill=C["red"] + (255,))
    d.text((W2 / 2 - tw(fb, txt) / 2, by + bh / 2 - 30), txt, font=fb, fill=(255, 255, 255, 255))
    return img


SPRITES = dict(statement=sp_statement, note=sp_note, cnt=sp_cnt, cards=sp_cards, rows=sp_rows, bars=sp_bars,
               vbars=sp_vbars, heat=sp_heat, dots=sp_dots, line=sp_line, waffle=sp_waffle, donut=sp_donut,
               chips=sp_chips, table=sp_table, timeline=sp_timeline, takeaways=sp_takeaways, endcard=sp_endcard)
ANIM = dict(cnt=0.9, cards=0.9, bars=0.7, vbars=1.1, waffle=0.9, donut=1.0, chips=0.6, timeline=1.1,
            takeaways=0.9, dots=1.4, heat=1.2)


def key_of(e):
    return json.dumps({k: v for k, v in e.items() if k not in ("at", "_hp", "_rp", "_vis")}, sort_keys=True, default=str)


_CACHE = {}


def sprite(e, p=1.0, now=None):
    if p >= 1 and now is None:
        k = key_of(e)
        if k not in _CACHE:
            if len(_CACHE) > 600:
                _CACHE.clear()
            _CACHE[k] = SPRITES[e["kind"]](e, 1.0, None)
        return _CACHE[k]
    return SPRITES[e["kind"]](e, p, now)


# ------------------------------------------------------------------ header (kicker + headline) and footer
_HDR = {}


def header_sprite(kicker, title):
    k = (kicker, title)
    if k not in _HDR:
        img = Image.new("RGBA", (1700, 170), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        fk = font("mono", 24, 800)
        if kicker:
            spaced(d, (0, 0), kicker, fk, C["amber"] + (255,), 5)
        if title:
            ft = font("grotesk", 58, 700)
            lines = wrap(title, ft, 1600)[:2]
            for i, l in enumerate(lines):
                d.text((0, 34 + i * 66), l, font=ft, fill=C["white"] + (255,))
        _HDR[k] = img
    return _HDR[k]


_SRC = {}


def source_sprite(text):
    if text not in _SRC:
        f = font("mono", 19, 500)
        img = Image.new("RGBA", (int(tw(f, text)) + 10, 30), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((0, 2), text, font=f, fill=C["source"] + (255,))
        _SRC[text] = img
    return _SRC[text]


# ------------------------------------------------------------------ timeline (alignment)
def spoken(text):
    return re.sub(r"(^|\s)@\w+\s*", r"\1", text).strip()


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


def chunk_ids():
    b = CHUNK_STARTS + [len(SEGMENTS)]
    return [list(range(b[i], b[i + 1])) for i in range(len(CHUNK_STARTS))]


def build_timeline():
    from sphinx_align import align
    os.makedirs(BUILD, exist_ok=True)
    segs = []
    for ci, ids in enumerate(chunk_ids()):
        path = os.path.join(TTS, f"chunk_{ci:02d}.wav")
        if not os.path.exists(path):
            print("missing", path)
            break
        path = slow_path(clean_path(path, ids))
        dur = len(read_wav(path)) / SR
        toks, starts = [], []
        for si in ids:
            starts.append(len(toks))
            toks += spoken(SEGMENTS[si]["text"]).split()
        times = align(path, toks)
        se = starts + [len(toks)]
        for k, si in enumerate(ids):
            a, b = se[k], se[k + 1]
            wf, wl = times[a][0], times[b - 1][1]
            pe = times[a - 1][1] if a > 0 else None
            ns = times[b][0] if b < len(toks) else None
            lead = 0.15 if pe is None else min(0.18, (wf - pe) / 2)
            trail = 0.3 if ns is None else min(0.18, (ns - wl) / 2)
            segs.append(dict(seg=si, path=path, cut_a=max(0.0, wf - lead), cut_b=min(dur, wl + trail),
                             tokens=toks[a:b], times=times[a:b], src_gap=(ns - wl) if ns is not None else 1.0))
    speech = sum(s["cut_b"] - s["cut_a"] for s in segs)
    n_sec = sum(1 for i, s in enumerate(segs) if i and SEGMENTS[s["seg"]]["kicker"] != SEGMENTS[segs[i - 1]["seg"]]["kicker"])
    n_para = sum(1 for s in segs[:-1] if s["src_gap"] >= 0.5)
    n_intra = len(segs) - 1 - n_para
    # scale gaps to land near TARGET seconds, within natural limits
    base_sec, base_para, base_intra = 0.9, 0.35, 0.10
    fixed = 0.6 + 3.0
    need = TARGET - speech - fixed
    unit = n_sec * base_sec + n_para * base_para + n_intra * base_intra
    k = float(np.clip(need / unit, 1.0, 2.6)) if unit else 1.0
    t = 0.6
    for i, s in enumerate(segs):
        if i:
            new_sec = SEGMENTS[s["seg"]]["kicker"] != SEGMENTS[segs[i - 1]["seg"]]["kicker"]
            t += k * (base_sec if new_sec else base_para if segs[i - 1]["src_gap"] >= 0.5 else base_intra)
        s["t0"] = t
        s["words"] = [(w, t + a - s["cut_a"], t + b - s["cut_a"]) for w, (a, b) in zip(s["tokens"], s["times"])]
        t += s["cut_b"] - s["cut_a"]
    total = t + 3.0
    for i, s in enumerate(segs):
        s["start"] = 0.0 if i == 0 else s["t0"] - 0.12
    for i, s in enumerate(segs):
        s["end"] = segs[i + 1]["start"] if i + 1 < len(segs) else total
    tl = dict(total=total, segments=segs, gap_scale=k)
    json.dump(tl, open(os.path.join(BUILD, "timeline.json"), "w"))
    print(f"timeline: {len(segs)} scenes, speech {speech:.0f}s, gap scale {k:.2f}, total {total:.1f}s ({total / 60:.1f} min)")
    return tl


# ------------------------------------------------------------------ scene logic
def marker_time(s, m):
    idx = 0
    for tok in SEGMENTS[s["seg"]]["text"].split():
        if tok.startswith("@"):
            if tok[1:] == m and s["words"]:
                return s["words"][min(idx, len(s["words"]) - 1)][1]
            continue
        idx += 1
    return None


def ident(e):
    if e["kind"] == "cnt":
        return json.dumps(["cnt", e["fmt"], e["to"], e.get("color"), e.get("label")])
    if e["kind"] in ("line", "heat", "dots", "takeaways"):
        return e["kind"]
    return key_of(e)


def prev_els(i):
    return SEGMENTS[i - 1]["elements"] if i > 0 else []


def persists(i, e):
    k = ident(e)
    return any(ident(p) == k for p in prev_els(i))


def appear_time(s, e, k):
    if e["kind"] == "heat" and persists(s["seg"], e):
        return -1e9  # the heatmap stays on screen; its 'at' only times the highlight
    if e.get("at"):
        t = marker_time(s, e["at"])
        if t is not None:
            return t - 0.08
    if persists(s["seg"], e):
        return -1e9
    i = s["seg"]
    new_section = i > 0 and SEGMENTS[i - 1]["kicker"] != SEGMENTS[i]["kicker"]
    return s["start"] + (0.34 if new_section else 0.15) + 0.09 * k


# ------------------------------------------------------------------ layout
_LAY = {}


def layout(i):
    if i in _LAY:
        return _LAY[i]
    els = SEGMENTS[i]["elements"]
    main = [e for e in els if e["kind"] != "note"]
    notes = [e for e in els if e["kind"] == "note"]
    sizes = [sprite(e).size for e in main]
    x0, y0, x1, y1 = CANVAS
    gap = 30
    total = sum(h for _, h in sizes) + gap * max(0, len(main) - 1)
    region = y1 - y0 - (70 if notes else 0)
    sc = min(1.0, region / total) if total else 1.0
    y = y0 + max(0, (region - total * sc) / 2)
    out = []
    for e, (w_, h_) in zip(main, sizes):
        w2, h2 = w_ * sc, h_ * sc
        if e["kind"] == "statement":
            x = x0
        else:
            x = (x0 + x1) / 2 - w2 / 2
        out.append((e, x, y, sc))
        y += h2 + gap * sc
    for e in notes:
        out.append((e, KX, NOTE_Y - 64, 1.0))
    _LAY[i] = out
    return out


# ------------------------------------------------------------------ frame
def dyn_sprite(e, s, t, ta):
    k = e["kind"]
    since = t - ta if ta > -1e8 else 99.0
    if k == "line":
        dr = e.get("draw")
        if dr:
            if dr == "s":
                d0, dur = s["start"] + 0.3, max(1.5, (s["end"] - s["start"]) * 0.8)
            else:
                d0, dur = (marker_time(s, dr) or s["start"]), 1.8
            p = (t - d0) / dur
            if p < 1:
                return sprite(e, max(0.0, p))
        return None
    if k == "heat":
        e2 = dict(e)
        hl_t = marker_time(s, e["at"]) if e.get("at") else s["start"]
        e2["_hp"] = max(0.0, min(1.0, (t - (hl_t or s["start"])) / 0.5)) if e.get("hl") else 1.0
        if e.get("reveal") == "rows" and since < 2.2:
            return sprite(e2, since / 2.2)
        if e.get("hl") and e2["_hp"] < 1:
            return sprite(e2, 1.0, now=t)
        return None
    if k == "dots":
        e2 = dict(e)
        rp = max(0.0, min(1.0, (since - 0.4) / 1.2)) if e.get("red") else 1.0
        e2["_rp"] = rp
        if since < 1.6:
            return sprite(e2, min(1.0, since / 1.0), now=t)
        return None
    if k == "vbars" and e.get("steps"):
        ts = [(marker_time(s, m) if m else s["start"] + 0.15) for m in e["steps"]]
        vis = [max(0.0, min(1.0, (t - (ti if ti is not None else s["start"])) / 0.8)) for ti in ts]
        if min(vis) < 1:
            return sprite(dict(e, _vis=vis), 1.0, now=t)
        return None
    if k == "endcard":
        return sprite(e, 1.0, now=since)
    if k in ANIM and since < ANIM[k]:
        if k == "cnt" and e.get("frm", 0) == e["to"]:
            return None
        return sprite(e, since / ANIM[k])
    return None


def comp(dst, spr, x, y):
    """Proper alpha compositing (paste() would square the alpha of translucent sprites)."""
    if x < 0 or y < 0:
        spr = spr.crop((max(0, -x), max(0, -y), spr.width, spr.height))
        x, y = max(0, x), max(0, y)
    if x >= dst.width or y >= dst.height:
        return
    spr = spr.crop((0, 0, min(spr.width, dst.width - x), min(spr.height, dst.height - y)))
    dst.alpha_composite(spr, (x, y))


def content_layer(si, s, t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for k, (e, x, y, sc) in enumerate(layout(si)):
        ta = appear_time(s, e, k)
        if t < ta:
            continue
        since = t - ta if ta > -1e8 else 99.0
        spr = dyn_sprite(e, s, t, ta) or sprite(e)
        a = ease(since / 0.45) if since < 0.45 else 1.0
        dy = 22 * (1 - a)
        if e["kind"] == "cnt" and e.get("frm", 0) != e["to"] and 0.9 <= since < 1.15:
            sc2 = sc * (1 + 0.05 * (1 - (since - 0.9) / 0.25))
        else:
            sc2 = sc
        spr = alpha_img(scaled(spr, sc2), a)
        full = sprite(e)
        fx = x + (full.width * sc - spr.width) / 2 if e["kind"] not in ("statement", "note") else x
        fy = y + (full.height * sc - spr.height) / 2
        comp(layer, spr, int(fx), int(fy + dy))
    return layer


def cam(s, t):
    i = s["seg"]
    if i > 0 and SEGMENTS[i - 1]["kicker"] == SEGMENTS[i]["kicker"]:
        return 1.0
    x = (t - s["start"]) / 0.7
    return 1.0 if x >= 1 else 0.965 + 0.035 * eio(max(0.0, x))


def zoomed(layer, z):
    bb = layer.getbbox()
    if not bb:
        return None
    crop = layer.crop(bb)
    spr = scaled(crop, z)
    cx, cy = W / 2, (CANVAS[1] + CANVAS[3]) / 2
    return spr, int(cx + (bb[0] - cx) * z), int(cy + (bb[1] - cy) * z)


TL = None
_FINAL = {}


def final_layer(si):
    if si not in _FINAL:
        _FINAL.clear()
        s = TL["segments"][si]
        te = s["end"] - 1e-3
        _FINAL[si] = zoomed(content_layer(s["seg"], s, te), cam(s, te))
    return _FINAL[si]


def header_state(si, t):
    s = TL["segments"][si]
    seg = SEGMENTS[s["seg"]]
    return seg["kicker"], seg["title"]


def render_frame(t, si):
    s = TL["segments"][si]
    seg = SEGMENTS[s["seg"]]
    frame = background().copy()
    tt = t - s["start"]
    prev = SEGMENTS[s["seg"] - 1] if s["seg"] > 0 else None
    new_section = prev is None or prev["kicker"] != seg["kicker"]
    first_persist = bool(seg["elements"]) and persists(s["seg"], seg["elements"][0]) and not seg["elements"][0].get("at")
    # outgoing content
    if si > 0 and not first_persist:
        dur = 0.32 if new_section else 0.28
        if tt < dur:
            p = eio(tt / dur)
            fl = final_layer(si - 1)
            if fl:
                spr, x, y = fl
                spr2 = alpha_img(spr, 1 - p)
                frame.paste(spr2, (int(x - (60 * p if new_section else 0)), int(y - (0 if new_section else 24 * p))), spr2)
    # header
    kp, tp = (prev["kicker"], prev["title"]) if prev else (None, None)
    k_, t_ = seg["kicker"], seg["title"]
    hdr = header_sprite(k_, t_)
    if (k_, t_) != (kp, tp) and tt < 0.45:
        a = ease(tt / 0.45)
        old = header_sprite(kp, tp)
        if tt < 0.2 and (kp, tp) != (None, None):
            o = alpha_img(old, 1 - tt / 0.2)
            frame.paste(o, (KX, KY), o)
        h2 = alpha_img(hdr, a)
        frame.paste(h2, (KX + int(-24 * (1 - a)) if k_ != kp else KX, KY), h2)
    else:
        frame.paste(hdr, (KX, KY), hdr)
    # content
    z = zoomed(content_layer(s["seg"], s, t), cam(s, t))
    if z:
        spr, x, y = z
        frame.paste(spr, (x, y), spr)
    if seg.get("src"):
        sp = source_sprite(seg["src"])
        a = min(1.0, max(0.0, (tt - 0.3) / 0.4))
        if prev and prev.get("src") == seg["src"]:
            a = 1.0
        sp = alpha_img(sp, a)
        frame.paste(sp, (KX, SRC_Y), sp)
    return frame


def load_tl():
    global TL
    TL = json.load(open(os.path.join(BUILD, "timeline.json")))
    return TL


def render_range(args):
    f0, f1, path = args
    if os.path.exists(path + ".done"):
        return path
    load_tl()
    segs = TL["segments"]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(PART_CRF),
                          "-tune", "animation", "-pix_fmt", "yuv444p", "-threads", "2", path], stdin=subprocess.PIPE)
    si = 0
    for f in range(f0, f1):
        t = f / FPS
        while si + 1 < len(segs) and t >= segs[si]["end"]:
            si += 1
        while si > 0 and t < segs[si]["start"]:
            si -= 1
        p.stdin.write(render_frame(t, si).tobytes())
    p.stdin.close()
    p.wait()
    if p.returncode == 0:
        open(path + ".done", "w").write("ok")
    return path


def render(t0=None, t1=None, workers=4, name="master.mp4"):
    """Frames -> near-lossless 4:4:4 master (BUILD/master.mp4). Use export() for the files to watch/upload."""
    load_tl()
    os.makedirs(OUT, exist_ok=True)
    f0 = int((t0 or 0) * FPS)
    f1 = int((t1 if t1 is not None else TL["total"]) * FPS)
    n = workers * 4
    step = math.ceil((f1 - f0) / n)
    tag = "" if t0 is None else f"r{f0}_"
    jobs = [(a, min(a + step, f1), os.path.join(BUILD, f"part_{tag}{i:02d}.mp4")) for i, a in enumerate(range(f0, f1, step))]
    with mp.Pool(workers) as pool:
        parts = pool.map(render_range, jobs, chunksize=1)
    lst = os.path.join(BUILD, "parts.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    out = os.path.join(BUILD, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-ss", f"{(t0 or 0):.3f}", "-t", f"{(f1 - f0) / FPS:.3f}", "-i", os.path.join(BUILD, "mix.wav"),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "pcm_s16le", "-shortest",
                    out.replace(".mp4", ".mov")], check=True)
    print("master:", out.replace(".mp4", ".mov"))
    return out.replace(".mp4", ".mov")


def export(master=None, name="video_v4", which=("4k", "1080p")):
    """master -> (1) 4K upload file for YouTube (lanczos 2x, high bitrate) and (2) a <95 MB 1080p file."""
    master = master or os.path.join(BUILD, "master.mov")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", master],
                               capture_output=True, text=True, check=True).stdout)
    if "4k" in which:
        up = os.path.join(OUT, f"{name}_4k.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", master, "-vf", "scale=3840:2160:flags=lanczos,format=yuv420p",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-tune", "animation", "-profile:v", "high",
                        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-movflags", "+faststart", up], check=True)
        print("4K:", up)
    if "1080p" not in which:
        return
    small = os.path.join(OUT, f"{name}.mp4")
    vb = int((95 * 8 * 1024 * 1024 / dur - 160000) / 1000)
    common = ["-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "slow", "-tune", "animation", "-b:v", f"{vb}k"]
    log = os.path.join(BUILD, "x264_2pass")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", master, *common, "-pass", "1", "-passlogfile", log, "-an",
                    "-f", "mp4", "/dev/null"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", master, *common, "-pass", "2", "-passlogfile", log,
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", small], check=True)
    print(f"1080p ({vb} kb/s):", small)


# ------------------------------------------------------------------ audio
def set_music_tempo(bpm):
    music.BPM = bpm
    music.BEAT = 60 / bpm
    music.BAR = 4 * music.BEAT
    music.CHORD_LEN = 2 * music.BAR
    music.BLOCK = music.CHORD_LEN * len(music.CHORDS)


def soft_click():
    n = int(0.03 * music.SR)
    t = np.arange(n) / music.SR
    s = np.sin(2 * np.pi * 2600 * t) * np.exp(-t / 0.004) * 0.12
    return np.stack([s, s], 1)


def build_audio():
    load_tl()
    total = TL["total"]
    n = int(total * SR) + 1
    voice = np.zeros(n, np.float32)
    cache = {}
    for s in TL["segments"]:
        if s["path"] not in cache:
            cache[s["path"]] = read_wav(s["path"])
        x = cache[s["path"]][int(s["cut_a"] * SR):int(s["cut_b"] * SR)].copy()
        f = min(len(x) // 2, int(0.015 * SR))
        if f:
            x[:f] *= np.linspace(0, 1, f); x[-f:] *= np.linspace(1, 0, f)
        st = int(s["t0"] * SR)
        voice[st:st + len(x)] += x[: n - st]
    vpath = os.path.join(BUILD, "voice.wav")
    with wave.open(vpath, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(voice, -1, 1) * 32767).astype("<i2").tobytes())
    set_music_tempo(100)
    rng_order = [0, 1, 1, 1, 0, 1, 1, 1]
    blocks, tt = [], 0.0
    rng = np.random.default_rng(11)
    i = 0
    while tt < total + music.BLOCK:
        blocks.append(music.block(rng_order[i % len(rng_order)], rng)); tt += music.BLOCK; i += 1
    m = music.simple_reverb(np.concatenate(blocks)[: int(total * music.SR)])
    fi, fo = int(2 * music.SR), int(5 * music.SR)
    m[:fi] *= np.linspace(0, 1, fi)[:, None]; m[-fo:] *= np.linspace(1, 0, fo)[:, None]
    m = m / (np.abs(m).max() + 1e-9) * 0.8
    sfx = np.zeros_like(m)

    def add(sound, t, g=1.0):
        if t is None:
            return
        st = max(0, int(t * music.SR))
        seg = sfx[st:st + len(sound)]
        seg += sound[: len(seg)] * g
    wh, pp, th, ck = music.swish(), music.pop(), music.thud(), soft_click()
    for i, s in enumerate(TL["segments"]):
        seg = SEGMENTS[s["seg"]]
        prev = SEGMENTS[s["seg"] - 1] if s["seg"] else None
        if prev is not None and prev["kicker"] != seg["kicker"]:
            add(wh, s["start"] - 0.05, 0.9)
        for k, e in enumerate(layout(s["seg"])):
            e = e[0]
            ta = appear_time(s, e, k)
            if ta < -1e8:
                continue
            if e["kind"] == "cnt" and e.get("frm", 0) != e["to"]:
                for j in range(8):
                    add(ck, ta + j * 0.09, 0.7)
            elif e["kind"] in ("cards", "takeaways", "endcard"):
                add(pp, ta, 0.35)
            elif e["kind"] == "statement":
                add(th, ta, 0.35)
    stereo = np.clip(m * 0.2 + sfx, -1, 1)
    mpath = os.path.join(BUILD, "music.wav")
    with wave.open(mpath, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(music.SR)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    apath = os.path.join(BUILD, "mix.wav")
    fc = ("[0:a]aresample=48000,loudnorm=I=-16:TP=-2:LRA=9,pan=stereo|c0=c0|c1=c0,asplit=2[v][vs];"
          "[1:a]volume=0.55[m];[m][vs]sidechaincompress=threshold=0.03:ratio=3:attack=30:release=500[md];"
          "[v][md]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-14:TP=-1.5:LRA=11,apad[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vpath, "-i", mpath, "-filter_complex", fc, "-map", "[out]",
                    "-t", f"{total:.3f}", "-ar", "48000", "-c:a", "pcm_s16le", apath], check=True)
    print("audio:", apath)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("timeline", "all"):
        build_timeline()
        build_audio()
    if cmd in ("render", "all"):
        a = [float(v) for v in sys.argv[2:4]]
        render(*(a or [None, None]), name=(f"preview_{int(a[0])}_{int(a[1])}.mp4" if a else "master.mp4"))
    if cmd in ("export", "all"):
        export(which=tuple(sys.argv[2:]) or ("4k", "1080p"))
