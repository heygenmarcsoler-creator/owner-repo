"""YouTube metadata for the 30-minute v3 video, in the channel's own description format."""
import json
import os

from script_v3 import SEGMENTS

HERE = os.path.dirname(os.path.abspath(__file__))
TL = json.load(open(os.path.join(HERE, "build", "v3", "timeline.json")))
N = json.load(open(os.path.join(HERE, "build", "v3_numbers.json")))

TITLE = "The AI Bubble in Europe: I Replayed the Dot-Com Crash on Your World ETF (Full Analysis)"
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
        "Is the AI boom a bubble, and what would it do to a European investor's world ETF? I replayed the dot-com "
        "crash with 27 years of real data in euros, stress-tested five popular portfolios and simulated 10,000 futures.",
        "",
        "One of the biggest losses in this replay wasn't caused by the market at all.",
        "",
        "CHAPTERS",
        *[f"{a} {b}" for a, b in ch],
        "",
        "KEY RESULTS (MSCI World, net, in EUR, 0.2% yearly fee)",
        "• €10,000 at the end of 1999: €5,515 by end 2002, back above €10,000 only in 2013, about €46,000 by August 2026",
        f"• {N['heat_negative']} of {N['heat_cells']} start-year × holding-period combinations (2000–2016, 1–10 years) lost money",
        "• €300 a month from January 2000: €96,000 in, about €416,000 today; pausing 2009–2013 cost about €108,000",
        "• Full dot-com replay on today's weights: MSCI World −45%, All-World −45%, equal weight −38%, 60/40 −24%",
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
    tags = ["AI bubble", "AI bubble Europe", "dot com crash", "MSCI World", "MSCI World ETF", "world ETF", "VWCE", "IWDA",
            "ETF investing Europe", "European investor", "stock market crash", "Monte Carlo simulation", "60/40 portfolio",
            "lump sum vs DCA", "concentration risk"]
    md = [f"# {TITLE}", "", f"Duration: {ts(TL['total'])}", "", "## Description", "", "```", desc, "```", "",
          "## Tags", "", ", ".join(tags), ""]
    open(os.path.join(HERE, "output", "youtube_metadata_v3.md"), "w").write("\n".join(md))
    print("\n".join(f"{a} {b}" for a, b in ch))


if __name__ == "__main__":
    main()
