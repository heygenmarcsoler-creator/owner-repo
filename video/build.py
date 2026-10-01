"""Assemble the full video: alignment -> timeline -> audio mix -> frames -> MP4.

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
SR_V = 24000
LEAD, TAIL = 0.5, 3.5
CHAPTER_GAP = 1.4
TARGET = float(os.environ.get("TARGET_SECONDS", 25 * 60))


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
    """Merge spelled letters (M S C I) and a few phrases into display words."""
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


# ------------------------------------------------------------------ timeline
def align_chunk(ci, seg_ids):
    from sphinx_align import align as sphinx_align
    toks, starts = [], []
    for si in seg_ids:
        ws = spoken(SEGMENTS[si]["text"]).split()
        starts.append(len(toks))
        toks += ws
    path = os.path.join(TTS, f"chunk_{ci:02d}.wav")
    try:
        times = sphinx_align(path, toks)
    except Exception as e:
        print("  sphinx failed, falling back to pause alignment:", e)
        from align import align as pause_align
        ends = {s - 1 for s in starts[1:]} | {len(toks) - 1}
        times, _ = pause_align(path, toks, ends)
    return toks, starts, times


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


def build_timeline():
    os.makedirs(BUILD, exist_ok=True)
    pieces = []  # (chunk audio array, a, b) per segment, in seconds within chunk
    segs = []
    for ci, seg_ids in enumerate(chunks()):
        path = os.path.join(TTS, f"chunk_{ci:02d}.wav")
        if not os.path.exists(path):
            print(f"chunk {ci} missing -> stopping timeline at segment {seg_ids[0]}")
            break
        x = read_wav(path)
        dur = len(x) / SR_V
        toks, starts, times = align_chunk(ci, seg_ids)
        starts_e = starts + [len(toks)]
        for k, si in enumerate(seg_ids):
            a_tok, b_tok = starts_e[k], starts_e[k + 1]
            w_first, w_last = times[a_tok][0], times[b_tok - 1][1]
            prev_end = times[a_tok - 1][1] if a_tok > 0 else 0.0
            next_start = times[b_tok][0] if b_tok < len(toks) else dur
            cut_a = 0.0 if k == 0 else (prev_end + w_first) / 2
            cut_b = dur if k == len(seg_ids) - 1 else (w_last + next_start) / 2
            segs.append(dict(seg=si, chunk=ci, cut_a=cut_a, cut_b=cut_b,
                             tokens=toks[a_tok:b_tok], times=times[a_tok:b_tok]))
            pieces.append((ci, cut_a, cut_b))
    speech = sum(s["cut_b"] - s["cut_a"] for s in segs)
    n_ch = sum(1 for s in segs if s["seg"] in CHAPTER_STARTS and s["seg"] != 0)
    fixed = LEAD + TAIL + n_ch * CHAPTER_GAP
    gap = (TARGET - speech - fixed) / max(1, len(segs) - 1)
    gap = float(np.clip(gap, 0.25, 0.9))
    t = LEAD
    for i, s in enumerate(segs):
        if i > 0:
            t += gap + (CHAPTER_GAP if s["seg"] in CHAPTER_STARTS else 0.0)
        s["t0"] = t  # global time where this segment's audio piece starts
        s["words"] = [(w, t + a - s["cut_a"], t + b - s["cut_a"]) for w, (a, b) in zip(s["tokens"], s["times"])]
        t += s["cut_b"] - s["cut_a"]
    total = t + TAIL
    # scene windows: from previous scene end to the start of the next
    for i, s in enumerate(segs):
        s["start"] = 0.0 if i == 0 else s["t0"] - (gap / 2 if s["seg"] not in CHAPTER_STARTS else 0.15)
    for i, s in enumerate(segs):
        s["end"] = segs[i + 1]["start"] if i + 1 < len(segs) else total
    tl = dict(total=total, gap=gap, segments=segs)
    json.dump(tl, open(os.path.join(BUILD, "timeline.json"), "w"))
    print(f"timeline: {len(segs)} segments, speech {speech:.0f}s, gap {gap:.2f}s, total {total:.1f}s ({total / 60:.1f} min)")
    return tl


# ------------------------------------------------------------------ audio
def build_audio(tl):
    total = tl["total"]
    n = int(total * SR_V) + 1
    voice = np.zeros(n, np.float32)
    cache = {}
    for s in tl["segments"]:
        ci = s["chunk"]
        if ci not in cache:
            cache[ci] = read_wav(os.path.join(TTS, f"chunk_{ci:02d}.wav"))
        x = cache[ci][int(s["cut_a"] * SR_V):int(s["cut_b"] * SR_V)].copy()
        f = min(len(x), int(0.01 * SR_V))
        if f:
            x[:f] *= np.linspace(0, 1, f)
            x[-f:] *= np.linspace(1, 0, f)
        st = int(s["t0"] * SR_V)
        voice[st:st + len(x)] += x[: n - st]
    vpath = os.path.join(BUILD, "voice.wav")
    with wave.open(vpath, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR_V)
        w.writeframes((np.clip(voice, -1, 1) * 32767).astype("<i2").tobytes())
    # music + sfx at 48k
    m = music.soundtrack(total) * 0.9
    sfx = np.zeros_like(m)

    def add(sound, t):
        st = int(t * music.SR)
        seg = sfx[st:st + len(sound)]
        seg += sound[: len(seg)]

    wh = music.whoosh()
    for s in tl["segments"]:
        if s["seg"] in CHAPTER_STARTS and s["seg"] != 0:
            add(wh, max(0, s["t0"] - 0.55))
        for e in SEGMENTS[s["seg"]]["elements"]:
            if e["kind"] == "big" and e.get("at"):
                add(music.pop() * 0.6, marker_time(s, e["at"]))
            if e["kind"] == "options" and e.get("countdown") and not prev_has(s, e):
                t0 = element_time(s, e)
                for k in range(3):
                    add(music.tick(), t0 + 0.6 + k)
    mpath = os.path.join(BUILD, "music.wav")
    stereo = np.clip(m * 0.22 + sfx, -1, 1)
    with wave.open(mpath, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(music.SR)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    apath = os.path.join(BUILD, "mix.m4a")
    fc = ("[0:a]aresample=48000,loudnorm=I=-16:TP=-2:LRA=9,pan=stereo|c0=c0|c1=c0,asplit=2[v][vs];"
          "[1:a]volume=0.55[m];"
          "[m][vs]sidechaincompress=threshold=0.03:ratio=3:attack=30:release=500[md];"
          "[v][md]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-14:TP=-1.5:LRA=11,apad[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vpath, "-i", mpath, "-filter_complex", fc,
                    "-map", "[out]", "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "192k", apath], check=True)
    print("audio:", apath)


# ------------------------------------------------------------------ scene helpers
_PREV = {}


def seg_by_index():
    return {s["seg"]: s for s in TL["segments"]}


def marker_time(s, marker):
    text = SEGMENTS[s["seg"]]["text"].split()
    idx = 0
    for tok in text:
        if tok.startswith("@"):
            if tok[1:] == marker:
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
    return E.el_key(e)


def prev_has(s, e):
    k = ident(e)
    return any(ident(p) == k for p in prev_elements(s))


def element_time(s, e):
    if prev_has(s, e) and not e.get("at"):
        return -1e9  # persisted from the previous scene: no entrance
    if e.get("at"):
        t = marker_time(s, e["at"])
        if t is not None:
            return t - 0.08
    return s["start"] + 0.05


def chart_in_prev(s):
    return any(p["kind"] == "chart" for p in prev_elements(s))


# ------------------------------------------------------------------ layout
SPACING = 34
LAYOUT_Y = {}


def final_sprite(e):
    return E.sprite_cached(E.el_key(e))


def layout(s):
    els = SEGMENTS[s["seg"]]["elements"]
    sizes = [final_sprite(e).size for e in els]
    if not els:
        return []
    region = E.CONTENT_BOTTOM - E.CONTENT_TOP
    sp = SPACING

    def tot(sp_):
        return sum(h for _, h in sizes) + sum(pair_gap(els[k], els[k + 1], sp_) for k in range(len(els) - 1))
    total = tot(sp)
    if total > region:
        sp = max(8, SPACING - (total - region) / max(1, len(els) - 1))
        total = tot(sp)
    y = E.CONTENT_TOP + (region - total) / 2
    # keep a persisting first element where it was in the previous scene
    i = s["seg"]
    if i > 0 and i - 1 in LAYOUT_Y and els and not els[0].get("at") and ident(els[0]) == LAYOUT_Y[i - 1][0]:
        y_prev = LAYOUT_Y[i - 1][1]
        if y_prev + total <= E.CONTENT_BOTTOM + 10:
            y = y_prev
    LAYOUT_Y[i] = (ident(els[0]), y)
    if y < E.CONTENT_TOP - 30:
        print(f"WARNING segment {s['seg']} overflows by {E.CONTENT_TOP - y:.0f}px")
    out = []
    for k, (e, (w, h)) in enumerate(zip(els, sizes)):
        out.append((e, (E.W - w) / 2, y, w, h))
        y += h + (pair_gap(e, els[k + 1], sp) if k + 1 < len(els) else 0)
    return out


def pair_gap(a, b, sp):
    return 6 if a["kind"] == b["kind"] and a["kind"] in ("bars", "rows") else sp


# ------------------------------------------------------------------ frame
def with_alpha(img, a):
    if a >= 0.999:
        return img
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return img


def dynamic_sprite(e, s, t, t_app):
    k = e["kind"]
    since = t - t_app
    if k == "big" and e.get("text") is None and e.get("frm", 0) != e["to"]:
        p = E.ease_out(since / 1.0)
        if p < 1:
            v = e.get("frm", 0) + (e["to"] - e.get("frm", 0)) * p
            ee = dict(e, to=v)
            return E.build_sprite(ee)
    if k in ("bars", "waffle") and since < 1.0 and t_app > -1e8:
        return E.build_sprite(e, prog=since / (0.7 if k == "bars" else 0.9))
    if k == "chart":
        draw = e.get("draw")
        if draw:
            if draw == "s":
                d0 = s["start"] + 0.2
                dur = max(1.5, (s["end"] - s["start"]) * 0.8)
            else:
                d0 = marker_time(s, draw) or s["start"]
                dur = 1.6
            p = (t - d0) / dur
            if p < 1:
                return E.build_sprite(e, prog=max(0.0, p))
    if k == "options":
        reveal_t = marker_time(s, e["reveal"]) if e.get("reveal") else None
        now = dict(t=since if t_app > -1e8 else 99, revealed=reveal_t is not None and t >= reveal_t)
        if since < 4.5 or now["revealed"] or t_app < -1e8:
            return E.build_sprite(e, now=now)
    return None


def render_frame(t, s, lay, base):
    frame = base.copy()
    for e, x, y, w, h in lay:
        if e["kind"] == "gap":
            continue
        t_app = element_time(s, e)
        if e["kind"] == "chart" and not e.get("at") and chart_in_prev(s):
            t_app = -1e9
        if t < t_app:
            continue
        since = t - t_app
        a = E.ease_out(since / 0.4) if t_app > -1e8 else 1.0
        dy = (1 - a) * 22
        spr = dynamic_sprite(e, s, t, t_app) or final_sprite(e)
        spr = with_alpha(spr, a)
        sx = int(x + (w - spr.width) / 2)
        sy = int(y + (h - spr.height) / 2 + dy)
        frame.paste(spr, (sx, sy), spr)
    src = SEGMENTS[s["seg"]].get("src")
    if src:
        sp = E.source_sprite(src)
        frame.paste(sp, ((E.W - sp.width) // 2, E.SOURCE_Y - sp.height // 2), sp)
    # captions
    for g in s["groups"]:
        g_start, g_end = g[0][1], g[-1][2] + 0.25
        if g_start - 0.05 <= t < g_end:
            active = 0
            for i, (_, a_, _b) in enumerate(g):
                if t >= a_ - 0.03:
                    active = i
            cs = E.caption_sprite(tuple(w for w, _, _ in g), active)
            frame.paste(cs, ((E.W - cs.width) // 2, E.CAPTION_Y - cs.height // 2), cs)
            break
    # progress bar
    d = ImageDraw.Draw(frame)
    d.rectangle((0, 0, int(E.W * t / TL["total"]), 7), fill=E.C["amber"])
    return frame


TL = None


def load_tl():
    global TL
    TL = json.load(open(os.path.join(BUILD, "timeline.json")))
    for s in TL["segments"]:
        s["groups"] = caption_groups(caption_words(s["tokens"], [(a, b) for _, a, b in s["words"]]))
    return TL


def render_range(args):
    f0, f1, path = args
    load_tl()
    base = E.background()
    segs = TL["segments"]
    lays = {}
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{E.W}x{E.H}", "-r", str(E.FPS), "-i", "-", "-c:v", "libx264",
                          "-preset", "veryfast", "-crf", "20", "-tune", "animation", "-pix_fmt", "yuv420p",
                          "-threads", "2", path], stdin=subprocess.PIPE)
    for k, s_ in enumerate(segs):
        lays[k] = layout(s_)
    si = 0
    for f in range(f0, f1):
        t = f / E.FPS
        while si + 1 < len(segs) and t >= segs[si]["end"]:
            si += 1
        while si > 0 and t < segs[si]["start"]:
            si -= 1
        s = segs[si]
        if si not in lays:
            lays[si] = layout(s)
        p.stdin.write(render_frame(t, s, lays[si], base).tobytes())
    p.stdin.close()
    p.wait()
    return path


def render(t0=None, t1=None, workers=4, name="video.mp4"):
    load_tl()
    os.makedirs(OUT, exist_ok=True)
    total = TL["total"]
    f0 = int((t0 or 0) * E.FPS)
    f1 = int((t1 if t1 is not None else total) * E.FPS)
    step = math.ceil((f1 - f0) / workers)
    jobs = [(a, min(a + step, f1), os.path.join(BUILD, f"part_{i}.mp4"))
            for i, a in enumerate(range(f0, f1, step))]
    with mp.Pool(len(jobs)) as pool:
        parts = pool.map(render_range, jobs)
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
        tl = build_timeline()
        TL = tl
        load_tl()
        build_audio(TL)
    if cmd in ("render", "all"):
        a = [float(v) for v in sys.argv[2:4]]
        if a:
            render(a[0], a[1], name=f"preview_{int(a[0])}_{int(a[1])}.mp4")
        else:
            render()
