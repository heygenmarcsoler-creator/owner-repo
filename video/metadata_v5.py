"""YouTube metadata for the ~8-minute v5 video (Trump vs the market), in the channel's description format."""
import json
import os

from script_v5 import SEGMENTS

HERE = os.path.dirname(os.path.abspath(__file__))
TL = json.load(open(os.path.join(HERE, "build", "v5", "timeline.json")))

TITLE = "Trump vs the Fed: 6 Forces Moving Your ETF Right Now"
THUMBNAIL = "output/thumbnail_v5.jpg"
CHAPTER_NAMES = {
    "TRUMP VS THE MARKET": "Intro: a hike instead of a cut",
    "1 · TRUMP VS THE FED": "1. Trump vs the Fed",
    "2 · THE OIL SHOCK": "2. The oil shock",
    "3 · THE BOND ALARM": "3. Bond yields at a 2002 high",
    "4 · THE AI MARKET": "4. The AI market",
    "5 · TARIFFS & THE DOLLAR": "5. Tariffs and the dollar",
    "6 · THE MIDTERMS": "6. The midterms",
    "WHAT IT MEANS FOR YOUR ETF": "Three scenarios for your ETF",
    "THE VERDICT": "Takeaways",
}


def ts(t):
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def chapters():
    out, last = [], None
    for s in TL["segments"]:
        k = SEGMENTS[s["seg"]]["kicker"]
        if k != last:
            out.append((0 if not out else s["start"], CHAPTER_NAMES.get(k, k.title())))
            last = k
    return out


def description():
    ch = chapters()
    lines = [
        "Trump demanded a 1% interest rate. The Fed raised rates instead, the US 10-year yield hit its highest level "
        "since 2002 and oil is above $100. Here are the 6 forces moving the stock market and your world ETF right now, with the numbers, "
        "for European investors (October 2026).",
        "",
        "CHAPTERS",
        *[f"{ts(a)} {b}" for a, b in ch],
        "",
        "KEY NUMBERS",
        "• Fed: +0.25% on 16 Sep 2026 to 3.75–4.00%, the first hike since 2023; Trump asked for 1% or less",
        "• Markets price an 86% chance of another Fed hike in December (CME FedWatch, early October)",
        "• US inflation 3.4% in August (spring peak ≈4.2%); core 2.4%, the lowest since March 2021; gasoline +27.4%",
        "• Brent: ≈$72 before the war (28 Feb) → $104.72 on 9 Oct; March +60%, the biggest monthly jump since 1988",
        "• Euro area inflation 3.8% in September (energy +18.8%); ECB deposit rate 2.50% after hikes in June and September",
        "• US 10-year yield 5.35% on 7 Oct, the highest since April 2002; US interest bill ≈$1.0T in fiscal 2026 (CBO)",
        "• S&P 500 earnings yield ≈2.4% (1 ÷ CAPE 41) vs 5.35% on the 10-year: the widest gap in favour of bonds since the dot-com era",
        "• Gold: record close $5,318 on 29 Jan, ≈22% lower in early October",
        "• S&P 500: 6,845.50 at the end of 2025 → record 7,844.52 (+14.6%); about −8% after the war began, record again on 15 April",
        "• Average effective US tariff rate: 2.4% (Jan 2025) → 14.3% → 10.5% → 11.8% (Yale Budget Lab, April 2026)",
        "• EUR/USD: 1.174 on 1 Jan → just above 1.20 in January → ≈1.12 in October; MSCI World in EUR +14.35% to 31 August",
        "• Midterms (3 Nov): average midterm-year fall 17.5% since 1950; the 12 months after every midterm since 1946 were positive",
        "",
        "SOURCES",
        "• Federal Reserve (FOMC statements); CME FedWatch; US Bureau of Labor Statistics (CPI, August 2026).",
        "• ICE Brent settlements; Trading Economics; EIA Short-Term Energy Outlook (August 2026).",
        "• Eurostat flash estimate (September 2026); ECB key interest rates and euro reference rates.",
        "• US Treasury yields (Bloomberg, CNBC, October 2026); Congressional Budget Office (fiscal 2026).",
        "• Shiller CAPE; S&P 500 closes (LSEG); MSCI World Net EUR index; Yale Budget Lab, State of U.S. Tariffs.",
        "• Carson Investment Research (FactSet), CFRA and U.S. Bank on midterm years; prediction markets (early October).",
        "• Office of Government Ethics filings via Yahoo Finance and SCMP (Q1 2026 trades).",
        "",
        "DISCLAIMER",
        "This video is for education only and is not financial advice. I'm not a licensed financial adviser. "
        "Scenarios are illustrations, not forecasts. Past performance does not guarantee future returns.",
        "",
        "Voiceover: Google Gemini TTS. Music: original, made for this channel.",
        "",
        "#Trump #FederalReserve #ETF",
    ]
    return "\n".join(lines), ch


def main():
    desc, ch = description()
    tags = ["trump stock market", "trump vs fed", "fed rate hike", "kevin warsh", "bond yields",
            "10 year treasury yield", "oil price", "strait of hormuz", "midterm elections stock market", "EUR/USD",
            "MSCI World", "world ETF", "ETF investing Europe", "stock market news", "stock market today"]
    assert len(desc) <= 5000 and len(", ".join(tags)) <= 500
    starts = [a for a, _ in ch]
    assert starts[0] == 0 and len(ch) >= 3 and min(b - a for a, b in zip(starts, starts[1:])) >= 10
    md = [f"# {TITLE}", "", f"Duration: {ts(TL['total'])}", "", f"Thumbnail: video/{THUMBNAIL}", "",
          "## Description", "", "```", desc, "```", "", "## Tags", "", ", ".join(tags), ""]
    open(os.path.join(HERE, "output", "youtube_metadata_v5.md"), "w").write("\n".join(md))
    print("\n".join(f"{ts(a)} {b}" for a, b in ch), f"\n{len(desc)} chars")


if __name__ == "__main__":
    main()
