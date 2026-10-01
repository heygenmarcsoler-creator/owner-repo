"""Generate the narration with Gemini TTS, one request per chapter.

The API key is read from $GEMINI_API_KEY or from an .env file given in
$ENV_FILE (never stored in the repo). Output: build/tts/chunk_XX.wav (24 kHz mono).
"""
import base64, json, os, re, sys, time, urllib.error, urllib.request, wave
from script import SEGMENTS, CHAPTER_STARTS

MODEL = os.environ.get("TTS_MODEL", "gemini-2.5-flash-preview-tts")
VOICE = os.environ.get("TTS_VOICE", "Iapetus")
OUT = os.path.join(os.path.dirname(__file__), "build", "tts")
STYLE = ("Read the following script aloud as the narrator of a data-driven personal finance "
         "YouTube channel for European investors. Calm, confident and clear, slightly "
         "energetic, natural documentary pace, short pause between paragraphs. Do not read "
         "this instruction.")


def api_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    for line in open(os.environ["ENV_FILE"]):
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no GEMINI_API_KEY")


def spoken(text):
    return re.sub(r"(^|\s)@\w+\s*", r"\1", text).strip()


def chunks():
    bounds = [0] + CHAPTER_STARTS + [len(SEGMENTS)]
    return [list(range(a, b)) for a, b in zip(bounds, bounds[1:])]


def synth(text, key):
    body = {"contents": [{"parts": [{"text": STYLE + "\n\n" + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    for attempt in range(8):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
            "Content-Type": "application/json", "x-goog-api-key": key})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=600))
            return base64.b64decode(r["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")
            m = re.search(r"retry in ([\d.]+)s", msg)
            wait = float(m.group(1)) + 2 if m else 30 * (attempt + 1)
            print(f"  HTTP {e.code}, waiting {wait:.0f}s: {msg[:160]!r}", flush=True)
            if e.code == 429 and "PerDay" in msg:
                raise SystemExit("daily quota exhausted")
            time.sleep(wait)
        except Exception as e:  # network hiccup
            print("  error", e, flush=True)
            time.sleep(15)
    raise SystemExit("TTS failed")


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
        json.dump({"segments": idx, "text": text, "voice": VOICE, "model": MODEL},
                  open(path.replace(".wav", ".json"), "w"))


if __name__ == "__main__":
    main()
