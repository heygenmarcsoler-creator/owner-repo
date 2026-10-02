"""Procedural background music (calm electronic bed, A minor, 96 BPM) + SFX.
Royalty-free by construction: everything is synthesised here."""
import numpy as np

SR = 48000
BPM = 112
BEAT = 60 / BPM
BAR = 4 * BEAT
CHORDS = [  # (root midi, chord tones midi)
    (45, [57, 60, 64, 69]),   # Am
    (41, [53, 57, 60, 65]),   # F
    (48, [55, 60, 64, 67]),   # C
    (43, [55, 59, 62, 67]),   # G
]
CHORD_LEN = 2 * BAR
BLOCK = CHORD_LEN * len(CHORDS)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def env_ad(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def pad_note(freq, n, rng):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det in (-0.0018, 0.0, 0.0021):
        f = freq * (1 + det)
        ph = rng.uniform(0, 2 * np.pi)
        for h in range(1, 7):
            out += np.sin(2 * np.pi * f * h * t + ph * h) / (h ** 1.6)
    att = np.minimum(1, t / 1.2)
    rel = np.minimum(1, (n / SR - t) / 1.2)
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.11 * t)
    return out * att * rel * lfo


def block(variant, rng):
    n = int(BLOCK * SR)
    L = np.zeros(n)
    R = np.zeros(n)
    cn = int(CHORD_LEN * SR)
    for ci, (root, tones) in enumerate(CHORDS):
        s = ci * cn
        # pad, spread in stereo
        for i, m in enumerate(tones):
            p = pad_note(hz(m), cn, rng) * 0.045
            pan = 0.3 + 0.4 * (i % 2)
            L[s:s + cn] += p * (1 - pan)
            R[s:s + cn] += p * pan
        # bass: soft pulse on beats 1 and 3
        for b in range(8):
            if b % 2 and variant < 2:
                continue
            bn = int(BEAT * 1.6 * SR)
            st = s + int(b * BEAT * SR)
            t = np.arange(bn) / SR
            note = np.sin(2 * np.pi * hz(root - 12) * t) * env_ad(bn, 0.02, 0.45) * 0.22
            L[st:st + bn] += note[: len(L[st:st + bn])]
            R[st:st + bn] += note[: len(R[st:st + bn])]
        # arpeggio pluck on 8ths
        if variant >= 1:
            pattern = [0, 2, 1, 3, 2, 1, 3, 2]
            for k in range(16):
                m = tones[pattern[k % 8]] + 12
                an = int(BEAT * SR)
                st = s + int(k * BEAT / 2 * SR)
                t = np.arange(an) / SR
                note = (np.sin(2 * np.pi * hz(m) * t) + 0.3 * np.sin(4 * np.pi * hz(m) * t)) * env_ad(an, 0.004, 0.18) * 0.05
                pan = 0.25 if k % 2 else 0.75
                seg = slice(st, min(st + an, n))
                L[seg] += note[: seg.stop - seg.start] * (1 - pan)
                R[seg] += note[: seg.stop - seg.start] * pan
        # kick on every beat (driving variants)
        if variant >= 2:
            for b in range(8):
                kn = int(0.25 * SR)
                st = s + int(b * BEAT * SR)
                t = np.arange(kn) / SR
                f = 45 + 90 * np.exp(-t / 0.04)
                k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.12) * 0.32
                L[st:st + kn] += k[: len(L[st:st + kn])]
                R[st:st + kn] += k[: len(R[st:st + kn])]
        # hats on off-beats
        if variant >= 2:
            for k in range(16):
                if k % 2 == 0:
                    continue
                hn = int(0.06 * SR)
                st = s + int(k * BEAT / 2 * SR)
                nz = rng.standard_normal(hn)
                nz = np.diff(np.concatenate([[0], nz]))  # crude high-pass
                h = nz * env_ad(hn, 0.001, 0.015) * 0.025
                L[st:st + hn] += h
                R[st:st + hn] += h
    return np.stack([L, R], 1)


def simple_reverb(x):
    out = x.copy()
    for d, g in ((0.031, 0.35), (0.047, 0.28), (0.071, 0.22), (0.113, 0.16), (0.167, 0.1)):
        k = int(d * SR)
        out[k:, 0] += x[:-k, 1] * g
        out[k:, 1] += x[:-k, 0] * g
    return out


def soundtrack(duration, seed=7):
    rng = np.random.default_rng(seed)
    order = [1, 2, 2, 2, 1, 2, 2, 2]
    blocks, total, i = [], 0.0, 0
    while total < duration + BLOCK:
        blocks.append(block(order[i % len(order)], rng))
        total += BLOCK
        i += 1
    x = np.concatenate(blocks)[: int(duration * SR)]
    x = simple_reverb(x)
    # fade in / out
    fi, fo = int(2 * SR), int(4 * SR)
    x[:fi] *= np.linspace(0, 1, fi)[:, None]
    x[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return x / (np.abs(x).max() + 1e-9) * 0.8


def whoosh(rng=None):
    rng = rng or np.random.default_rng(1)
    n = int(0.7 * SR)
    t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    # sweep a resonant band-pass by mixing differentiated noise with a moving one-pole filter
    out = np.zeros(n)
    y = 0.0
    for i in range(n):
        a = 0.02 + 0.5 * (i / n)
        y = y + a * (nz[i] - y)
        out[i] = y
    e = np.sin(np.pi * np.clip(t / 0.7, 0, 1)) ** 2
    return np.stack([out * e, out * e], 1) * 0.35


def tick():
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * 1800 * t) * np.exp(-t / 0.008) * 0.25
    return np.stack([s, s], 1)


def pop():
    n = int(0.18 * SR)
    t = np.arange(n) / SR
    f = 220 + 500 * np.exp(-t / 0.03)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.05) * 0.3
    return np.stack([s, s], 1)


def swish():
    rng = np.random.default_rng(3)
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    out = np.zeros(n)
    y = 0.0
    for i in range(n):
        a = 0.05 + 0.6 * (i / n)
        y = y + a * (nz[i] - y)
        out[i] = nz[i] - y  # high-passed, rising
    e = np.sin(np.pi * t / t[-1]) ** 3
    s = out * e * 0.10
    return np.stack([s, s], 1)


def thud():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 50 + 110 * np.exp(-t / 0.03)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.1) * 0.55
    rng = np.random.default_rng(5)
    s += rng.standard_normal(n) * np.exp(-t / 0.015) * 0.12
    return np.stack([s, s], 1)


def ding():
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * 1318.5 * t) + 0.6 * np.sin(2 * np.pi * 1975.5 * t)) * np.exp(-t / 0.28) * 0.16
    s[int(0.08 * SR):] += (np.sin(2 * np.pi * 1760 * t) * np.exp(-t / 0.3) * 0.12)[: n - int(0.08 * SR)]
    return np.stack([s, s], 1)


def riser(length=1.1):
    rng = np.random.default_rng(9)
    n = int(length * SR)
    t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    out = np.zeros(n)
    y = 0.0
    for i in range(n):
        a = 0.01 + 0.4 * (i / n) ** 2
        y = y + a * (nz[i] - y)
        out[i] = y
    s = out * (t / length) ** 2 * 0.5
    return np.stack([s, s], 1)
