"""Assemble the full video: alignment -> timeline -> audio mix -> frames -> MP4.

v2: faster pacing (voice tempo, trimmed pauses, per-sentence scenes), silent
"pause & guess" beats, camera moves, scene transitions, pop/slam/wipe entrances,
chapter openers, chapter tracker and segmented progress bar.

Usage:
  python3 build.py timeline            # align + timeline.json + audio
  python3 build.py render [t0 t1]      # render (optionally only a time range)
  python3 build.py all
"""
import json
import math
import multiprocessing as mp
import os
import re
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

import engine as E
import music
from script import SEGMENTS, CHAPTER_STARTS, CH
from tts import chunks, spoken

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(HERE, "output")
TTS = os.path.join(BUILD, "tts")
TTS_FAST = os.path.join(BUILD, "tts_fast")
SR_V = 24000
TEMPO = float(os.environ.get("TEMPO", 1.05))
LEAD, TAIL = 0.3, 3.0
CHAPTER_PRE = 1.1      # silence before a chapter's narration (opener animation)
INTRA_GAP = 0.03       # between sentences of the same paragraph
PARA_GAP = 0.12        # between paragraphs
MAX_EDGE = 0.13        # max silence kept on each side of a segment
TRANS = 0.22           # scene transition length


# ------------------------------------------------------------------ captions text
SEQ_REPL = [
    (["s", "and", "p", "five", "hundred"], "S&P 500"),
    (["nasdaq", "one", "hundred"], "NASDAQ-100"),
    (["euro", "stoxx", "fifty"], "EURO STOXX 50"),
    (["sixty", "forty"], "60/40"),
]


def clean(tok):
    return re.sub(r"[^\w&'%-]", "", tok.lower())


def caption_words(tokens, times):
    out, i = [], 0
    while i < len(tokens):
        done = False
        for seq, disp in SEQ_REPL:
            n = len(seq)
            if [clean(t) for t in tokens[i:i + n]] == seq:
                trail = re.sub(r"[\w&'%-]", "", tokens[i + n - 1])
                out.append((disp + trail, times[i][0], times[i + n - 1][1]))
                i += n
                done = True
                break
        if done:
            continue
        if re.fullmatch(r"[A-Z]", tokens[i]):
            j = i
            while j < len(tokens) and re.fullmatch(r"[A-Z][.,?!]?", tokens[j]):
                j += 1
                if not re.fullmatch(r"[A-Z]", tokens[j - 1]):
                    break
            if j - i >= 2:
                out.append(("".join(tokens[i:j]), times[i][0], times[j - 1][1]))
                i = j
                continue
        out.append((tokens[i], times[i][0], times[i][1]))
        i += 1
    return [(w.upper(), a, b) for w, a, b in out]


def caption_groups(words):
    groups, cur = [], []
    for w in words:
        cur.append(w)
        chars = sum(len(x[0]) for x in cur)
        if len(cur) >= 3 or chars >= 18 or re.search(r"[.,?!:;]$", w[0]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


# ------------------------------------------------------------------ audio helpers
def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


def fast_path(ci):
    os.makedirs(TTS_FAST, exist_ok=True)
    src = os.path.join(TTS, f"chunk_{ci:02d}.wav")
    dst = os.path.join(TTS_FAST, f"chunk_{ci:02d}_{TEMPO:.3f}.wav")
    if not os.path.exists(dst):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", f"atempo={TEMPO}",
                        "-ar", str(SR_V), "-ac", "1", dst], check=True)
    return dst


def align_chunk(path, seg_ids):
    from sphinx_align import align as sphinx_align
    toks, starts = [], []
    for si in seg_ids:
        ws = spoken(SEGMENTS[si]["text"]).split()
        starts.append(len(toks))
        toks += ws
    try:
        times = sphinx_align(path, toks)
    except Exception as e:
        print("  sphinx failed, falling back to pause alignment:", e)
        from align import align as pause_align
        ends = {s - 1 for s in starts[1:] if s > 0} | {len(toks) - 1}
        times, _ = pause_align(path, toks, ends)
    return toks, starts, times


# ------------------------------------------------------------------ timeline
def build_timeline():
    os.makedirs(BUILD, exist_ok=True)
    segs = []
    for ci, seg_ids in enumerate(chunks()):
        if not os.path.exists(os.path.join(TTS, f"chunk_{ci:02d}.wav")):
            print(f"chunk {ci} missing -> stopping timeline at segment {seg_ids[0]}")
            break
        path = fast_path(ci)
        dur = len(read_wav(path)) / SR_V
        toks, starts, times = align_chunk(path, seg_ids)
        starts_e = starts + [len(toks)]
        for k, si in enumerate(seg_ids):
            a, b = starts_e[k], starts_e[k + 1]
            if a == b:
                segs.append(dict(seg=si, silent=True, hold=SEGMENTS[si].get("hold", 3.0), path=None,
                                 tokens=[], times=[], src_gap=1.0))
                continue
            w_first, w_last = times[a][0], times[b - 1][1]
            prev_end = times[a - 1][1] if a > 0 else None
            next_start = times[b][0] if b < len(toks) else None
            lead = MAX_EDGE if prev_end is None else min(MAX_EDGE, (w_first - prev_end) / 2)
            trail = 0.25 if next_start is None else min(MAX_EDGE, (next_start - w_last) / 2)
            segs.append(dict(seg=si, silent=False, path=path, cut_a=max(0.0, w_first - lead),
                             cut_b=min(dur, w_last + trail), tokens=toks[a:b], times=times[a:b],
                             src_gap=(next_start - w_last) if next_start is not None else 1.0))
    t = LEAD
    for i, s in enumerate(segs):
        if i > 0:
            prev = segs[i - 1]
            if s["seg"] in CHAPTER_STARTS:
                t += CHAPTER_PRE
            elif prev["silent"] or s["silent"]:
                t += 0.08
            else:
                t += INTRA_GAP if prev["src_gap"] < 0.55 else PARA_GAP
        s["t0"] = t
        if s["silent"]:
            s["words"] = []
            t += s["hold"]
        else:
            s["words"] = [(w, t + a - s["cut_a"], t + b - s["cut_a"]) for w, (a, b) in zip(s["tokens"], s["times"])]
            t += s["cut_b"] - s["cut_a"]
    total = t + TAIL
    for i, s in enumerate(segs):
        if i == 0:
            s["start"] = 0.0
        elif s["seg"] in CHAPTER_STARTS:
            s["start"] = s["t0"] - CHAPTER_PRE
        else:
            s["start"] = s["t0"] - (0.02 if s["silent"] else 0.06)
    for i, s in enumerate(segs):
        s["end"] = segs[i + 1]["start"] if i + 1 < len(segs) else total
    speech = sum(s["cut_b"] - s["cut_a"] for s in segs if not s["silent"])
    tl = dict(total=total, segments=segs, tempo=TEMPO)
    json.dump(tl, open(os.path.join(BUILD, "timeline.json"), "w"))
    print(f"timeline: {len(segs)} scenes, speech {speech:.0f}s, total {total:.1f}s ({total / 60:.1f} min)")
    return tl


# ------------------------------------------------------------------ audio
def build_audio(tl):
    total = tl["total"]
    n = int(total * SR_V) + 1
    voice = np.zeros(n, np.float32)
    cache = {}
    for s in tl["segments"]:
        if s["silent"]:
            continue
        if s["path"] not in cache:
            cache[s["path"]] = read_wav(s["path"])
        x = cache[s["path"]][int(s["cut_a"] * SR_V):int(s["cut_b"] * SR_V)].copy()
        f = min(len(x) // 2, int(0.012 * SR_V))
        if f:
            x[:f] *= np.linspace(0, 1, f)
            x[-f:] *= np.linspace(1, 0, f)
        st = int(s["t0"] * SR_V)
        voice[st:st + len(x)] += x[: n - st]
    vpath = os.path.join(BUILD, "voice.wav")
    with wave.open(vpath, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR_V)
        w.writeframes((np.clip(voice, -1, 1) * 32767).astype("<i2").tobytes())

    m = music.soundtrack(total) * 0.9
    sfx = np.zeros_like(m)

    def add(sound, t, gain=1.0):
        if t is None:
            return
        st = max(0, int(t * music.SR))
        seg = sfx[st:st + len(sound)]
        seg += sound[: len(seg)] * gain

    wh, sw, th, dg, ri, pp, tk = music.whoosh(), music.swish(), music.thud(), music.ding(), music.riser(), music.pop(), music.tick()
    for i, s in enumerate(tl["segments"]):
        seg = SEGMENTS[s["seg"]]
        if s["seg"] in CHAPTER_STARTS and s["seg"] != 0:
            add(ri, s["start"] - 0.6, 0.8)
            add(wh, s["start"] - 0.1)
            add(th, s["start"] + 0.35, 0.7)
        elif i > 0 and not first_persists(s):
            add(sw, s["start"] - 0.06, 0.9)
        for k, e in enumerate(seg["elements"]):
            ta = element_time(s, e, k)
            if ta < -1e8:
                continue
            kind = e["kind"]
            if kind in ("big", "donut", "versus", "card", "boxes", "pill"):
                add(pp, ta, 0.55)
            if kind in ("stamp", "strike2"):
                add(th, ta + (0.12 if kind == "stamp" else 0.0), 0.9)
            if kind == "options":
                if e.get("countdown") and not prev_has(s, e):
                    for j in range(3):
                        add(tk, ta + 0.6 + j)
                if e.get("reveal"):
                    add(dg, marker_time(s, e["reveal"]))
            if kind == "timer":
                for j in range(int(e.get("seconds", 3))):
                    add(tk, ta + j, 1.2)
            if kind == "subscribe":
                add(tk, ta + 1.1, 1.5)
                add(dg, ta + 1.2, 0.6)
    mpath = os.path.join(BUILD, "music.wav")
    stereo = np.clip(m * 0.26 + sfx, -1, 1)
    with wave.open(mpath, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(music.SR)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    apath = os.path.join(BUILD, "mix.m4a")
    fc = ("[0:a]aresample=48000,loudnorm=I=-16:TP=-2:LRA=9,pan=stereo|c0=c0|c1=c0,asplit=2[v][vs];"
          "[1:a]volume=0.6[m];"
          "[m][vs]sidechaincompress=threshold=0.03:ratio=3:attack=30:release=400[md];"
          "[v][md]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-14:TP=-1.5:LRA=11,apad[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vpath, "-i", mpath, "-filter_complex", fc,
                    "-map", "[out]", "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "128k", apath], check=True)
    print("audio:", apath)


# ------------------------------------------------------------------ scene helpers
def marker_time(s, marker):
    idx = 0
    for tok in SEGMENTS[s["seg"]]["text"].split():
        if tok.startswith("@"):
            if tok[1:] == marker and s["words"]:
                return s["words"][min(idx, len(s["words"]) - 1)][1]
            continue
        idx += 1
    return None


def prev_elements(s):
    i = s["seg"]
    return SEGMENTS[i - 1]["elements"] if i > 0 else []


def ident(e):
    if e["kind"] == "big" and e.get("text") is None:
        return json.dumps(["big", e["fmt"], e["to"], e.get("color"), e.get("size")])
    if e["kind"] == "chart":
        return "chart"
    return E.el_key({k: v for k, v in e.items() if k not in ("until", "delay")})


def prev_has(s, e):
    k = ident(e)
    return any(ident(p) == k and not p.get("until") for p in prev_elements(s))


def first_persists(s):
    els = SEGMENTS[s["seg"]]["elements"]
    return bool(els) and prev_has(s, els[0]) and not els[0].get("at")


def element_time(s, e, k=0):
    if prev_has(s, e) and not e.get("at"):
        return -1e9
    if e.get("at"):
        t = marker_time(s, e["at"])
        if t is not None:
            return t - 0.08
    return s["start"] + 0.04 + e.get("delay", 0.0) + 0.07 * k


def until_time(s, e):
    return marker_time(s, e["until"]) - 0.1 if e.get("until") and marker_time(s, e["until"]) else None


def chart_in_prev(s):
    return any(p["kind"] == "chart" for p in prev_elements(s))


# ------------------------------------------------------------------ layout
SPACING = 34
LAYOUT_Y = {}


def fit(spr):
    """Shrink sprites wider than the frame (vertical Shorts)."""
    if spr is not None and spr.width > E.W - 60:
        return scaled(spr, (E.W - 60) / spr.width)
    return spr


def final_sprite(e):
    return fit(E.sprite_cached(E.el_key(e)))


def pair_gap(a, b, sp):
    return 6 if a["kind"] == b["kind"] and a["kind"] in ("bars", "rows") else sp


OVERLAY = {"pause", "timer"}


def overlay_pos(e):
    w, h = final_sprite(e).size
    if e["kind"] == "pause":
        return (e, E.W - 60 - w, 70, w, h)
    return (e, E.W - 70 - w, 200, w, h)


def layout(s):
    all_els = SEGMENTS[s["seg"]]["elements"]
    els = [e for e in all_els if e["kind"] not in OVERLAY]
    if not els:
        return [overlay_pos(e) for e in all_els if e["kind"] in OVERLAY]
    # elements sharing a 'slot' occupy the same place (swapped with at/until)
    slots, order = {}, []
    for e in els:
        key = e.get("slot") or id(e)
        if key not in slots:
            slots[key] = []
            order.append(key)
        slots[key].append(e)
    sizes = {key: (max(final_sprite(e).width for e in slots[key]), max(final_sprite(e).height for e in slots[key]))
             for key in order}
    region = E.CONTENT_BOTTOM - E.CONTENT_TOP
    firsts = [slots[k][0] for k in order]

    def tot(sp_):
        return sum(sizes[k][1] for k in order) + sum(pair_gap(firsts[j], firsts[j + 1], sp_) for j in range(len(order) - 1))
    sp = SPACING
    total = tot(sp)
    if total > region:
        sp = max(8, SPACING - (total - region) / max(1, len(order) - 1))
        total = tot(sp)
    y = E.CONTENT_TOP + (region - total) / 2
    i = s["seg"]
    if i > 0 and i - 1 in LAYOUT_Y and not els[0].get("at") and ident(els[0]) == LAYOUT_Y[i - 1][0]:
        if LAYOUT_Y[i - 1][1] + total <= E.CONTENT_BOTTOM + 10:
            y = LAYOUT_Y[i - 1][1]
    LAYOUT_Y[i] = (ident(els[0]), y)
    if y < E.CONTENT_TOP - 30:
        print(f"WARNING segment {i} overflows by {E.CONTENT_TOP - y:.0f}px")
    pos = {}
    for j, key in enumerate(order):
        w, h = sizes[key]
        pos[key] = (y, h)
        y += h + (pair_gap(firsts[j], firsts[j + 1], sp) if j + 1 < len(order) else 0)
    out = [overlay_pos(e) for e in all_els if e["kind"] in OVERLAY]
    for e in els:
        key = e.get("slot") or id(e)
        yy, h = pos[key]
        w = final_sprite(e).width
        if e["kind"] == "ticker":
            out.append((e, 0, 72, E.W, 96))
        else:
            out.append((e, (E.W - w) / 2, yy, w, h))
    return out


# ------------------------------------------------------------------ element animation
POP = {"big", "stamp", "donut", "timer", "pause", "boxes", "card", "subscribe", "pill"}
WIPE = {"head", "sub"}


def with_alpha(img, a):
    if a >= 0.999:
        return img
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return img


def scaled(img, sc):
    if abs(sc - 1) < 0.004:
        return img
    return img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), Image.BILINEAR)


def dynamic_sprite(e, s, t, t_app):
    k = e["kind"]
    since = t - t_app if t_app > -1e8 else 99.0
    if k == "big" and e.get("text") is None and e.get("frm", 0) != e["to"]:
        p = E.ease_out(since / 0.8)
        if p < 1:
            return E.build_sprite(dict(e, to=e.get("frm", 0) + (e["to"] - e.get("frm", 0)) * p))
    if k in ("bars", "waffle") and since < 0.9:
        return E.build_sprite(e, prog=since / (0.55 if k == "bars" else 0.8))
    if k == "chips" and since < E.PROG["chips"]:
        return E.build_sprite(e, prog=since / E.PROG["chips"])
    if k == "chart":
        draw = e.get("draw")
        if draw:
            if draw == "s":
                d0, dur = s["start"] + 0.15, max(1.2, (s["end"] - s["start"]) * 0.75)
            else:
                d0, dur = (marker_time(s, draw) or s["start"]), 1.3
            p = (t - d0) / dur
            if p < 1:
                return E.build_sprite(e, prog=max(0.0, p))
    if k == "options":
        reveal_t = marker_time(s, e["reveal"]) if e.get("reveal") else None
        now = dict(t=since, revealed=reveal_t is not None and t >= reveal_t)
        if since < 4.5 or now["revealed"]:
            return E.build_sprite(e, now=now)
    if k in E.TIMED and since < E.TIMED[k]:
        return E.build_sprite(e, now=dict(t=since))
    if k in E.PROG and since < E.PROG[k]:
        return E.build_sprite(e, prog=since / E.PROG[k])
    return None


def place(layer, spr, cx, cy):
    layer.paste(spr, (int(cx - spr.width / 2), int(cy - spr.height / 2)), spr)


def content_layer(s, lay, t):
    layer = Image.new("RGBA", (E.W, E.H), (0, 0, 0, 0))
    for k, (e, x, y, w, h) in enumerate(lay):
        if e["kind"] == "gap":
            continue
        t_app = element_time(s, e, k)
        if e["kind"] == "chart" and not e.get("at") and chart_in_prev(s):
            t_app = -1e9
        if t < t_app:
            continue
        tu = until_time(s, e)
        out_a = 1.0
        if tu is not None and t >= tu:
            out_a = 1 - E.ease_out((t - tu) / 0.18)
            if out_a <= 0:
                continue
        since = t - t_app if t_app > -1e8 else 99.0
        spr = fit(dynamic_sprite(e, s, t, t_app)) or final_sprite(e)
        cx, cy = x + w / 2, y + h / 2
        kind = e["kind"]
        a, sc, dx, dy = 1.0, 1.0, 0.0, 0.0
        if since < 0.5:
            p = since / 0.32
            if kind == "stamp":
                sc = 1.9 - 0.9 * E.ease_out(since / 0.16)
                a = min(1, since / 0.08)
            elif kind in POP:
                sc = 0.55 + 0.45 * E.ease_out_back(p)
                a = E.ease_out(since / 0.18)
            elif kind in WIPE:
                wp = E.ease_out(since / 0.38)
                if wp < 1:
                    spr = spr.crop((0, 0, max(1, int(spr.width * wp)), spr.height))
                    cx = x + w / 2 - (final_sprite(e).width - spr.width) / 2 if kind != "chart" else cx
                a = E.ease_out(since / 0.2)
                dy = 10 * (1 - wp)
            elif kind in ("tag",):
                a = E.ease_out(p)
                dy = -14 * (1 - a)
            else:
                a = E.ease_out(p)
                dy = 28 * (1 - a)
        # count-up punch + red shake
        if kind == "big" and e.get("text") is None and e.get("frm", 0) != e["to"] and 0.8 <= since < 1.0:
            sc *= 1 + 0.07 * (1 - (since - 0.8) / 0.2)
        if kind in ("big", "strike2") and e.get("color", "white") == "red" and since < 0.45:
            dx = 9 * math.sin(since * 70) * (1 - since / 0.45)
        if kind == "stamp" and since < 0.3:
            dx = 6 * math.sin(since * 90) * (1 - since / 0.3)
        if out_a < 1:
            a *= out_a
            sc *= 0.94 + 0.06 * out_a
        spr = with_alpha(scaled(spr, sc), a)
        if kind in WIPE and since < 0.5:
            layer.paste(spr, (int(x + (w - final_sprite(e).width) / 2), int(cy - spr.height / 2 + dy)), spr)
        else:
            place(layer, spr, cx + dx, cy + dy)
    return layer


def zoom_of(s, t):
    if SEGMENTS[s["seg"]].get("cam") == "none":
        return 1.0
    span = max(0.5, s["end"] - s["start"])
    return 1.0 + 0.035 * E.ease_in_out((t - s["start"]) / span)


def zoomed(layer, z, shift=(0, 0), extra=1.0, alpha=1.0):
    """Scale the content layer about the frame centre; returns (sprite, x, y)."""
    bb = layer.getbbox()
    if not bb:
        return None
    crop = layer.crop(bb)
    zz = z * extra
    spr = scaled(crop, zz)
    spr = with_alpha(spr, alpha)
    cx, cy = E.W / 2, E.H / 2
    x = cx + (bb[0] - cx) * zz + shift[0]
    y = cy + (bb[1] - cy) * zz + shift[1]
    return spr, int(x), int(y)


# ------------------------------------------------------------------ frame
TL = None
LAYS = {}
FINAL_CACHE = {}
CH_BOUNDS = []


def final_layer(si):
    if si not in FINAL_CACHE:
        s = TL["segments"][si]
        te = s["end"] - 1e-3
        FINAL_CACHE.clear()
        FINAL_CACHE[si] = zoomed(content_layer(s, LAYS[si], te), zoom_of(s, te))
    return FINAL_CACHE[si]


def chapter_index(t):
    k = 0
    for j, b in enumerate(CH_BOUNDS):
        if t >= b:
            k = j
    return k


def render_frame(t, si, segs):
    s = segs[si]
    frame = E.background_at(t).copy()
    E.draw_particles(frame, t)
    tt = t - s["start"]
    is_ch = s["seg"] in CHAPTER_STARTS and s["seg"] != 0
    # outgoing scene
    if si > 0 and not first_persists(s):
        dur = 0.35 if is_ch else TRANS
        if tt < dur:
            p = E.ease_in_out(tt / dur)
            prev = final_layer(si - 1)
            if prev:
                spr, x, y = prev
                if is_ch:
                    spr2 = with_alpha(spr, 1 - p)
                    frame.paste(spr2, (int(x - 700 * p * p), y), spr2)
                else:
                    sc = 1 - 0.05 * p
                    spr2 = with_alpha(scaled(spr, sc), 1 - p)
                    frame.paste(spr2, (int(x + spr.width * (1 - sc) / 2), int(y + spr.height * (1 - sc) / 2 - 40 * p)), spr2)
    z = zoomed(content_layer(s, LAYS[si], t), zoom_of(s, t))
    if z:
        spr, x, y = z
        frame.paste(spr, (x, y), spr)
    src = SEGMENTS[s["seg"]].get("src")
    if src:
        sp = E.source_sprite(src)
        a = min(1.0, max(0.0, (tt - 0.2) / 0.3))
        sp = with_alpha(sp, a)
        frame.paste(sp, ((E.W - sp.width) // 2, E.SOURCE_Y - sp.height // 2), sp)
    for g in s["groups"]:
        g_start, g_end = g[0][1], g[-1][2] + 0.18
        if g_start - 0.05 <= t < g_end:
            active = 0
            for i, (_, a_, _b) in enumerate(g):
                if t >= a_ - 0.03:
                    active = i
            cs = E.caption_sprite(tuple(w for w, _, _ in g), active)
            pop = E.ease_out_back((t - g_start + 0.05) / 0.14)
            cs = scaled(cs, (0.85 + 0.15 * pop) * min(1.0, (E.W - 40) / cs.width))
            frame.paste(cs, ((E.W - cs.width) // 2, E.CAPTION_Y - cs.height // 2), cs)
            break
    # chapter tracker + segmented progress bar
    if not E.VERTICAL:
        k = chapter_index(t)
        label = "INTRO" if k == 0 else f"{k:02d} · {CH[k - 1].upper()}"
        tr = E.tracker_sprite(label)
        frame.paste(tr, (40, 26), tr)
    d = ImageDraw.Draw(frame)
    bounds = CH_BOUNDS + [TL["total"]]
    gap = 6
    for j in range(len(CH_BOUNDS)):
        a, b = bounds[j], bounds[j + 1]
        x0 = E.W * a / TL["total"] + (gap / 2 if j else 0)
        x1 = E.W * b / TL["total"] - (gap / 2 if j < len(CH_BOUNDS) - 1 else 0)
        d.rectangle((x0, 0, x1, 7), fill=(26, 34, 50))
        xf = min(x1, E.W * t / TL["total"])
        if xf > x0:
            d.rectangle((x0, 0, xf, 7), fill=E.C["amber"])
    return frame


def load_tl():
    global TL, CH_BOUNDS
    TL = json.load(open(os.path.join(BUILD, "timeline.json")))
    for s in TL["segments"]:
        s["groups"] = caption_groups(caption_words(s["tokens"], [(a, b) for _, a, b in s["words"]]))
    CH_BOUNDS = [0.0] + [s["start"] for s in TL["segments"] if s["seg"] in CHAPTER_STARTS and s["seg"] != 0]
    return TL


def render_range(args):
    f0, f1, path = args
    if os.path.exists(path + ".done"):
        return path
    load_tl()
    segs = TL["segments"]
    for k, s_ in enumerate(segs):
        LAYS[k] = layout(s_)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{E.W}x{E.H}", "-r", str(E.FPS), "-i", "-", "-c:v", "libx264",
                          "-preset", "medium", "-crf", "26", "-tune", "animation", "-pix_fmt", "yuv420p",
                          "-threads", "2", path], stdin=subprocess.PIPE)
    si = 0
    for f in range(f0, f1):
        t = f / E.FPS
        while si + 1 < len(segs) and t >= segs[si]["end"]:
            si += 1
        while si > 0 and t < segs[si]["start"]:
            si -= 1
        p.stdin.write(render_frame(t, si, segs).tobytes())
    p.stdin.close()
    p.wait()
    if p.returncode == 0:
        open(path + ".done", "w").write(f"{f0} {f1}\n")
    return path


def render(t0=None, t1=None, workers=4, name="video.mp4"):
    load_tl()
    os.makedirs(OUT, exist_ok=True)
    total = TL["total"]
    f0 = int((t0 or 0) * E.FPS)
    f1 = int((t1 if t1 is not None else total) * E.FPS)
    nparts = workers * 3
    step = math.ceil((f1 - f0) / nparts)
    jobs = [(a, min(a + step, f1), os.path.join(BUILD, f"part_{i:02d}.mp4"))
            for i, a in enumerate(range(f0, f1, step))]
    with mp.Pool(workers) as pool:
        parts = pool.map(render_range, jobs, chunksize=1)
    lst = os.path.join(BUILD, "parts.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    out = os.path.join(OUT, name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-ss", f"{(t0 or 0):.3f}", "-t", f"{(f1 - f0) / E.FPS:.3f}", "-i", os.path.join(BUILD, "mix.m4a"),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart",
                    "-shortest", out], check=True)
    print("video:", out)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("timeline", "all"):
        build_timeline()
        load_tl()
        build_audio(TL)
    if cmd in ("render", "all"):
        a = [float(v) for v in sys.argv[2:4]]
        if a:
            render(a[0], a[1], name=f"preview_{int(a[0])}_{int(a[1])}.mp4")
        else:
            render()
