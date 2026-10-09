"""Gemini TTS for the v3/v4 (channel-format) script: one request per chunk, natural speed (no time-stretch)."""
import json
import os
import re
import sys
import wave

from script_v3 import SEGMENTS, CHUNK_STARTS
from tts import synth, api_key
import tts as T

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", os.environ.get("TTS_DIR", "tts_v4"))
T.VOICE = os.environ.get("TTS_VOICE", "Charon")
T.MODEL = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")
T.STYLE = ("Read the following script aloud as the narrator of a data-driven personal finance documentary "
           "for European investors. Warm, natural and human, like an experienced presenter talking to one person. "
           "Keep a steady, natural speaking pace, neither rushed nor slow, with short natural pauses between "
           "paragraphs. Clear articulation of every number; no hype. Do not read this instruction.")


def spoken(text):
    return re.sub(r"(^|\s)@\w+\s*", r"\1", text).strip()


def chunks():
    b = CHUNK_STARTS + [len(SEGMENTS)]
    return [list(range(b[i], b[i + 1])) for i in range(len(CHUNK_STARTS))]


def main():
    os.makedirs(OUT, exist_ok=True)
    key = api_key()
    only = set(int(a) for a in sys.argv[1:])
    for ci, idx in enumerate(chunks()):
        path = os.path.join(OUT, f"chunk_{ci:02d}.wav")
        if (only and ci not in only) or (not only and os.path.exists(path)):
            continue
        text = "\n\n".join(spoken(SEGMENTS[i]["text"]) for i in idx)
        words = len(text.split())
        print(f"chunk {ci}: segments {idx[0]}-{idx[-1]}, {words} words", flush=True)
        pcm = synth(text, key)
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        dur = len(pcm) / 48000
        print(f"  -> {dur:.1f}s ({words / dur * 60:.0f} wpm)", flush=True)
        json.dump({"segments": idx, "text": text, "voice": T.VOICE, "model": T.MODEL}, open(path.replace(".wav", ".json"), "w"))


if __name__ == "__main__":
    main()
