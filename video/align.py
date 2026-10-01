"""Word timings for a TTS chunk without an ASR model.

Detects pauses in the audio and matches them (dynamic programming) to the
word boundaries of the known text, weighting sentence/paragraph ends. Words
between two matched pauses are spread by syllable count.
"""
import re
import wave

import numpy as np

HOP = 0.01


def load_wav(path):
    with wave.open(path) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    return x, sr


NUM_SYL = {"0": 2, "1": 1, "2": 1, "3": 1, "4": 1, "5": 1, "6": 2, "7": 2, "8": 1, "9": 1}


def syllables(word):
    w = word.lower()
    digits = re.sub(r"\D", "", w)
    if digits:
        if len(digits) == 4:  # a year: "twenty thirteen"
            return 4
        return max(1, sum(NUM_SYL[d] for d in digits) + len(digits) // 3)
    w = re.sub(r"[^a-z]", "", w)
    if not w:
        return 1
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")):
        n -= 1
    if len(w) == 1:  # spelled letters: "M S C I"
        n = 1 if w not in "w" else 3
    return max(1, n)


def boundary_strength(word, para_end):
    if para_end:
        return 3.0
    if re.search(r"[.?!]['\"”’]?$", word):
        return 2.2
    if re.search(r"[,;:—–]$", word):
        return 1.0
    return 0.0


def detect_pauses(x, sr, min_len=0.11):
    hop = int(sr * HOP)
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    loud = np.percentile(db[db > -50], 60) if np.any(db > -50) else -20
    thr = max(loud - 26, -55)
    sil = db < thr
    pauses, i = [], 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            pauses.append((i * HOP, j * HOP))
            i = j
        else:
            i += 1
    speech_start = pauses[0][1] if pauses and pauses[0][0] == 0 else 0.0
    speech_end = pauses[-1][0] if pauses and pauses[-1][1] >= n * HOP - 1e-6 else n * HOP
    inner = [(a, b) for a, b in pauses if a > speech_start + 1e-6 and b < speech_end - 1e-6 and b - a >= min_len]
    return inner, speech_start, speech_end


def align(path, words, para_ends):
    """words: list of tokens as spoken; para_ends: set of word indices that end a segment.
    Returns list of (start, end) per word."""
    x, sr = load_wav(path)
    pauses, s0, s1 = detect_pauses(x, sr)
    N = len(words)
    syl = np.array([syllables(w) + 0.35 for w in words], float)
    cum = np.concatenate([[0], np.cumsum(syl)]) / syl.sum()  # fraction before word k
    strength = np.array([boundary_strength(words[k], k in para_ends) for k in range(N - 1)])
    # speech-only fraction at each pause
    total_pause = sum(b - a for a, b in pauses)
    speech_total = (s1 - s0) - total_pause
    acc, fr = 0.0, []
    prev = s0
    for a, b in pauses:
        acc += a - prev
        fr.append(acc / speech_total)
        prev = b
    M = len(pauses)
    bfrac = cum[1:N]  # boundary k (after word k) -> fraction of syllables before word k+1
    miss = np.where(strength >= 3, 1.6, np.where(strength >= 2, 1.0, np.where(strength >= 1, 0.25, 0.0)))
    P = np.concatenate([[0], np.cumsum(miss)])  # P[k] = sum miss[0..k-1]
    INF = 1e18
    K = N - 1
    dp = np.full(K + 1, INF)  # dp[k+1]: last matched boundary k; dp[0]: none
    dp[0] = 0.0
    back = []
    for j, (a, b) in enumerate(pauses):
        plen = b - a
        dev = np.abs(bfrac - fr[j]) * speech_total  # seconds
        bonus = strength * min(1.0, plen / 0.35)
        cost = dev * 1.2 - bonus * 0.9 + (0.25 if plen < 0.2 else 0.0)
        cost = np.where(strength == 0, cost + 0.6 + plen * 2.0, cost)
        # best previous (k' < k) including the 'none' state
        prevv = dp - np.concatenate([[0], P[1:K + 1]])  # value adjusted by misses up to k'
        runmin = np.minimum.accumulate(prevv)
        argmin = np.zeros(K + 1, int)
        best = 0
        for i in range(K + 1):
            if prevv[i] <= prevv[best]:
                best = i
            argmin[i] = best
        # matching pause j to boundary k uses previous states 0..k (state index k means last boundary k-1)
        match = cost + P[0:K] + runmin[0:K]
        skip = dp + 0.4 + plen * 0.5
        new = skip.copy()
        choose = np.full(K + 1, -1)
        better = match < new[1:]
        new[1:] = np.where(better, match, new[1:])
        choose[1:] = np.where(better, argmin[0:K], -1)
        back.append(choose)
        dp = new
    final = dp + (P[K] - np.concatenate([[0], P[1:K + 1]]))
    k = int(np.argmin(final))
    anchors = {}
    for j in range(M - 1, -1, -1):
        c = back[j][k]
        if c >= 0:
            anchors[k - 1] = pauses[j]
            k = c
    # build spans between anchors
    times = [None] * N
    bounds = sorted(anchors)
    starts = [0] + [bk + 1 for bk in bounds]
    ends = [bk for bk in bounds] + [N - 1]
    t_starts = [s0] + [anchors[bk][1] for bk in bounds]
    t_ends = [anchors[bk][0] for bk in bounds] + [s1]
    for ws, we, ts, te in zip(starts, ends, t_starts, t_ends):
        seg = syl[ws:we + 1]
        span = max(te - ts, 0.05)
        c = np.concatenate([[0], np.cumsum(seg)]) / seg.sum()
        for i in range(len(seg)):
            times[ws + i] = (ts + c[i] * span, ts + c[i + 1] * span)
    info = dict(pauses=M, anchors=len(anchors), strong=int((strength >= 2).sum()),
                strong_matched=sum(1 for bk in anchors if strength[bk] >= 2), duration=len(x) / sr)
    return times, info
