"""YouTube metadata for the 30-minute v3/v4 video, in the channel's own description format."""
import json
import os

from script_v3 import SEGMENTS

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.environ.get("BUILD_DIR", "v4")
TL = json.load(open(os.path.join(HERE, "build", BUILD_DIR, "timeline.json")))
N = json.load(open(os.path.join(HERE, "build", "v3_numbers.json")))

TITLE = "Is AI a Bubble? I Replayed 2000 on Your World ETF"
THUMBNAIL = "output/thumbnail_v4.jpg"
CHAPTER_NAMES = {
    "THE AI BUBBLE IN EUROPE": "Intro",
    "WHAT YOU OWN": "What your world ETF really owns",
    "IS IT A BUBBLE?": "Is it a bubble? 2000 vs 2026",
    "WE'VE BEEN HERE BEFORE": "Japan 1989 and the dot-com crash",
    "ROUND 1 · THE LUMP SUM": "Round 1: €10,000 at the 1999 top",
    "EVERY START, EVERY HORIZON": "Every start year × every holding period",
    "ROUND 2 · THE MONTHLY SAVER": "Round 2: €300 a month",
    "THE CURRENCY LAYER": "The currency layer",
    "ROUND 3 · THE STRESS TEST": "Round 3: stress-testing 5 portfolios",
    "THE FUTURE · SIMULATION": "10,000 simulated futures",
    "WHAT ACTUALLY HELPED": "What actually helped",
    "THE PRICE OF PANIC": "The price of panic",
    "MY CHECKLIST · NOT ADVICE": "My checklist",
    "THE VERDICT": "Verdict",
}


def ts(t):
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def chapters():
    out, last = [], None
    for s in TL["segments"]:
        k = SEGMENTS[s["seg"]]["kicker"]
        if k != last:
            out.append((ts(0 if not out else s["start"]), CHAPTER_NAMES.get(k, k.title())))
            last = k
    return out


def description():
    ch = chapters()
    lines = [
        "Is AI a bubble, and what would a dot-com style crash do to your MSCI World ETF? I replayed 2000–2002 "
        "with 27 years of real euro data, stress-tested 5 portfolios and simulated 10,000 futures.",
        "",
        "The biggest loss in this replay wasn't caused by the market at all.",
        "",
        "CHAPTERS",
        *[f"{a} {b}" for a, b in ch],
        "",
        "KEY RESULTS (MSCI World, net, in EUR, 0.2% yearly fee)",
        "• €10,000 at the end of 1999: €5,515 by end 2002, back above €10,000 only in 2013, about €46,000 by August 2026",
        f"• {N['heat_negative']} of {N['heat_cells']} start-year × holding-period combinations (2000–2016, 1–10 years) lost money",
        "• €300 a month from January 2000: €96,000 in, about €416,000 today; pausing 2009–2013 cost about €108,000",
        "• The monthly plan was back in profit 3 years after the 2002 bottom (2 years after 2008); the lump sum needed 13",
        "• Full dot-com replay on today's weights: MSCI World −45%, All-World −45%, equal weight −38%, 60/40 −24%",
        "• Climbing back at each portfolio's own historical growth: ≈10.5 years for MSCI World, ≈5.5 years for 60/40",
        f"• 10,000 futures starting with a 2000–2002 crash: median {N['mc_crash_recover_median_years']:.0f} years to break even, "
        f"{N['mc_crash_not_recovered_20y_pct']}% not back within 20 years",
        "• Selling at the end of 2002: €8,813 today vs €46,032 for staying invested",
        "",
        "DATA & METHOD",
        "• MSCI World net total return in EUR, annual year-end values 2000–2025 plus 2026 to the end of August; 0.2% yearly fee.",
        "• MSCI World in USD and ECB euro reference rates for the currency section.",
        "• Euro area government bonds (all maturities, approximate index returns) for 60/40 and 80/20, rebalanced yearly.",
        "• Monthly plan approximated with annual returns (mid-year contributions).",
        "• Simulation: 10,000 paths × 20 years, 3-year block bootstrap of annual returns 2000–2025; crash-start version forces 2000, 2001, 2002 first.",
        "• Stress test: today's MSCI World split into AI giants (≈25%), rest of US (≈46%), other developed (≈29%); illustrative scenarios, not forecasts.",
        "• Other sources: ECB Blog (Aug 2026), Shiller CAPE, S&P 500 concentration data, ETFGI, justETF, Nikkei 225, Euro Stoxx 50, Morningstar Mind the Gap.",
        "",
        "DISCLAIMER",
        "This video is for education only and is not financial advice. I'm not a licensed financial adviser. "
        "Past performance does not guarantee future returns.",
        "",
        "Voiceover: Google Gemini TTS. Music: original, made for this channel.",
        "",
        "#AIBubble #MSCIWorld #ETF",
    ]
    return "\n".join(lines), ch


def main():
    desc, ch = description()
    tags = ["is AI a bubble", "AI bubble", "AI bubble 2026", "dot com crash", "MSCI World", "MSCI World ETF", "VWCE",
            "IWDA", "FTSE All-World", "world ETF", "ETF investing Europe", "stock market crash", "equal weight ETF",
            "60/40 portfolio", "Monte Carlo simulation"]
    assert len(desc) <= 5000 and len(", ".join(tags)) <= 500
    md = [f"# {TITLE}", "", f"Duration: {ts(TL['total'])}", "", f"Thumbnail: video/{THUMBNAIL}", "",
          "## Description", "", "```", desc, "```", "", "## Tags", "", ", ".join(tags), ""]
    open(os.path.join(HERE, "output", f"youtube_metadata_{BUILD_DIR}.md"), "w").write("\n".join(md))
    print("\n".join(f"{a} {b}" for a, b in ch))


if __name__ == "__main__":
    main()
