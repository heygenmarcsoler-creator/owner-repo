"""Forced alignment of the TTS audio against the known script (PocketSphinx)."""
import subprocess

from pocketsphinx import Decoder

from sphinx_norm import normalise

EXTRA = {
    "broadcom": "B R AO D K AA M", "bucket's": "B AH K AH T S", "covid": "K OW V IH D",
    "etf": "IY T IY EH F", "etf's": "IY T IY EH F S", "etfs": "IY T IY EH F S",
    "maths": "M AE TH S", "stoxx": "S T AA K S",
}


def pcm16k(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000",
                           "-f", "s16le", "-"], check=True, capture_output=True).stdout


def align(path, tokens):
    """tokens: original words. Returns [(start, end)] per token, in seconds."""
    norm = [normalise(t) or ["uh"] for t in tokens]
    flat = [w for ws in norm for w in ws]
    d = Decoder(samprate=16000, bestpath=False, loglevel="FATAL", beam=1e-80, wbeam=1e-60, pbeam=1e-80)
    items = list(EXTRA.items())
    for i, (w, ph) in enumerate(items):
        d.add_word(w, ph, i == len(items) - 1)
    d.set_align_text(" ".join(flat))
    d.start_utt()
    d.process_raw(pcm16k(path), full_utt=True)
    d.end_utt()
    if d.hyp() is None:
        raise RuntimeError("alignment failed")
    got = [(seg.word.split("(")[0], seg.start_frame / 100, (seg.end_frame + 1) / 100) for seg in d.seg()]
    words = [g for g in got if not g[0].startswith("<") and g[0] not in ("[noise]", "sil")]
    if len(words) != len(flat):
        raise RuntimeError(f"alignment length mismatch {len(words)} != {len(flat)}")
    out, i = [], 0
    for ws in norm:
        out.append((words[i][1], words[i + len(ws) - 1][2]))
        i += len(ws)
    return out
