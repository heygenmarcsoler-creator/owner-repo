"""Gemini TTS for the v3 (channel-format) script: one request per chunk, calm pace."""
import json
import os
import re
import sys
import wave

from script_v3 import SEGMENTS, CHUNK_STARTS
from tts import synth, api_key
import tts as T

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build", "tts_v3")
T.STYLE = ("Read the following script aloud as the narrator of a calm, data-driven personal finance documentary "
           "for European investors. Measured, unhurried and authoritative, like a BBC documentary narrator; "
           "clear articulation of every number; no hype; short natural pause between paragraphs. "
           "Do not read this instruction.")


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
        json.dump({"segments": idx, "text": text}, open(path.replace(".wav", ".json"), "w"))


if __name__ == "__main__":
    main()
