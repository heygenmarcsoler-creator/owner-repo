"""Vertical Shorts (1080x1920) cut from the long video, each with a new hook.

  python3 shorts.py tts       # one Gemini request for all five hooks
  python3 shorts.py build     # timelines, audio and render for every Short
  python3 shorts.py build 2   # just one
"""
import json
import os
import subprocess
import sys
import wave

os.environ["VERTICAL"] = "1"

import numpy as np  # noqa: E402

import build as B  # noqa: E402
import script as SC  # noqa: E402
from script import S, head, sub, big, count, stamp, donut, chips, pill  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SBUILD = os.path.join(HERE, "build", "shorts")
LONG_TL = os.path.join(HERE, "build", "timeline.json")

SHORTS = [
    dict(slug="sold-vs-waited", segs=(326, 345),
         hook="Your ETF drops forty-five percent. What you do next could cost you thirty-seven thousand euros, and almost nobody gets it right.",
         title="You Lose 45%. What You Do Next Costs €37,000",
         els=[head("{r:SOLD} or {g:WAITED?}", size=120), count(37000, "€{:,.0f}?", color="amber", size=170)]),
    dict(slug="japan-1989", segs=(76, 91),
         hook="Your world ETF has been this concentrated once before. Almost nobody remembers what it cost: thirty-four years.",
         title="Your World ETF Was This Concentrated Once Before (Japan 1989)",
         els=[head("JAPAN 1989 = {a:AI 2026?}", size=104), donut(42, "Japan, share of world stocks", color="red")]),
    dict(slug="13-years", segs=(139, 155),
         hook="You buy a world ETF at the worst moment in twenty-six years. How long until you stop losing money?",
         title="€10,000 in a World ETF at the 1999 Top: How Long to Break Even?",
         els=[head("€10,000 → {a:???}", size=130), stamp("WORST TIMING", angle=-6, size=96)]),
    dict(slug="euro-trap", segs=(198, 207),
         hook="Your US stock doesn't move all year, but you still lose nine percent. Why? Almost nobody checks this.",
         title="Your US Stock Didn't Move. You Still Lost 9% (Euro Investors)",
         els=[head("THE {a:EURO TRAP}", size=130), big("$ → €", color="amber", size=200)]),
    dict(slug="amazon-90", segs=(365, 373),
         hook="You can be right about AI and still lose ninety percent. Why? Ask anyone who bought Amazon in 1999.",
         title="Right About AI, Still Down 90%? Ask Amazon Investors",
         els=[head("RIGHT ≠ {r:RICH}", size=140), chips(["Amazon · 1999"])]),
]
HOOK_BASE = len(SC.SEGMENTS)


def hooks_text():
    return "\n\n".join(s["hook"] for s in SHORTS)


def cmd_tts():
    from tts import synth, api_key
    os.makedirs(SBUILD, exist_ok=True)
    pcm = synth(hooks_text(), api_key())
    p = os.path.join(SBUILD, "hooks_raw.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    print("hooks audio:", p, f"{len(pcm) / 48000:.1f}s")


def hooks_audio():
    raw = os.path.join(SBUILD, "hooks_raw.wav")
    fast = os.path.join(SBUILD, f"hooks_{B.TEMPO:.3f}.wav")
    if not os.path.exists(fast):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", f"atempo={B.TEMPO}", "-ar", "24000",
                        "-ac", "1", fast], check=True)
    from sphinx_align import align
    toks = [w for s in SHORTS for w in s["hook"].split()]
    times = align(fast, toks)
    out, i = [], 0
    dur = len(B.read_wav(fast)) / 24000
    for k, s in enumerate(SHORTS):
        n = len(s["hook"].split())
        tt = times[i:i + n]
        nxt = times[i + n][0] if i + n < len(times) else dur
        out.append(dict(path=fast, tokens=s["hook"].split(), times=tt,
                        cut_a=max(0.0, tt[0][0] - 0.05), cut_b=min(nxt, tt[-1][1] + 0.12)))
        i += n
    return out


def install_hook_segments():
    for k, s in enumerate(SHORTS):
        seg = S(s["hook"], *s["els"], cam=None)
        if len(SC.SEGMENTS) <= HOOK_BASE + k:
            SC.SEGMENTS.append(seg)


def build_short(k, hook):
    s = SHORTS[k]
    long_tl = json.load(open(LONG_TL))
    a, b = s["segs"]
    picked = [dict(x) for x in long_tl["segments"] if a <= x["seg"] <= b]
    t = 0.25
    segs = []
    hs = dict(seg=HOOK_BASE + k, silent=False, path=hook["path"], cut_a=hook["cut_a"], cut_b=hook["cut_b"],
              tokens=hook["tokens"], times=hook["times"], src_gap=1.0, t0=t)
    hs["words"] = [(w, t + x - hs["cut_a"], t + y - hs["cut_a"]) for w, (x, y) in zip(hs["tokens"], hs["times"])]
    t += hs["cut_b"] - hs["cut_a"]
    segs.append(hs)
    t += 0.25
    shift = t - picked[0]["t0"]
    for x in picked:
        x["t0"] += shift
        x["words"] = [(w, p + shift, q + shift) for w, p, q in x["words"]]
        segs.append(x)
    last = segs[-1]
    total = last["t0"] + (last["hold"] if last["silent"] else last["cut_b"] - last["cut_a"]) + 0.6
    for i, x in enumerate(segs):
        x["start"] = 0.0 if i == 0 else x["t0"] - (0.02 if x["silent"] else 0.06)
    for i, x in enumerate(segs):
        x["end"] = segs[i + 1]["start"] if i + 1 < len(segs) else total
    d = os.path.join(SBUILD, f"{k + 1}-{s['slug']}")
    os.makedirs(d, exist_ok=True)
    tl = dict(total=total, segments=segs, tempo=B.TEMPO)
    json.dump(tl, open(os.path.join(d, "timeline.json"), "w"))
    # the previous scene inside the Short (not in the long video) drives persistence
    order = [x["seg"] for x in segs]
    prev_map = {order[i]: (order[i - 1] if i else None) for i in range(len(order))}

    def prev_elements(seg_dict):
        p = prev_map.get(seg_dict["seg"])
        return SC.SEGMENTS[p]["elements"] if p is not None else []
    B.prev_elements = prev_elements
    B.BUILD = d
    B.CHAPTER_STARTS = []
    B.LAYOUT_Y.clear()
    B.FINAL_CACHE.clear()
    B.load_tl()
    B.build_audio(B.TL)
    for f in os.listdir(d):
        if f.startswith("part_"):
            os.remove(os.path.join(d, f))
    out = B.render(name=f"short_{k + 1}_{s['slug']}.mp4")
    print(f"short {k + 1}: {total:.1f}s -> {out}")
    return out, total


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "tts":
        return cmd_tts()
    install_hook_segments()
    hooks = hooks_audio()
    only = [int(x) - 1 for x in sys.argv[2:]] or range(len(SHORTS))
    for k in only:
        build_short(k, hooks[k])


if __name__ == "__main__":
    main()
