"""YouTube title/description/chapters/tags + thumbnail, from the built timeline."""
import json
import os

from PIL import Image, ImageDraw

import engine as E
from script import CH, CHAPTER_STARTS, X, WORLD

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")

TITLE = "The AI Bubble in Europe: I Replayed the Dot-Com Crash on Your World ETF"
ALT_TITLES = [
    "If the AI Bubble Pops, What Happens to Your MSCI World ETF? (Euro Data 1999–2026)",
    "Your “Diversified” World ETF Is 70% USA: I Stress-Tested It With Real Euro Crashes",
]
TAGS = ["ai bubble", "ai bubble 2026", "msci world", "msci world etf", "dot com crash", "dot com bubble",
        "stock market crash", "european investor", "etf europe", "vwce", "ftse all world", "msci acwi",
        "equal weight etf", "nvidia", "magnificent 7", "concentration risk", "euro investing",
        "index investing europe", "passive investing", "60/40 portfolio europe", "ecb ai bubble", "euroindexlab"]


def ts(t):
    t = int(t)
    return f"{t // 60}:{t % 60:02d}" if t < 3600 else f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def description(tl):
    by_seg = {s["seg"]: s for s in tl["segments"]}
    chapters = [("0:00", "€440 billion you didn't know you owned")]
    for i, si in enumerate(CHAPTER_STARTS):
        if si in by_seg:
            chapters.append((ts(by_seg[si]["start"]), f"{i + 1}. {CH[i]}"))
    lines = [
        "European households hold around €440 billion in US tech stocks, mostly through world ETFs, "
        "and most don't know it. With US valuations at their second-highest level in 150 years, I replayed "
        "the dot-com crash with real euro data (MSCI World, net, in EUR, 1999–2026) and stress-tested the "
        "portfolios Europeans actually hold today: MSCI World, All-World/ACWI, equal weight, Europe-only and 60/40.",
        "",
        "In this video:",
        "• How long €10,000 invested at the 1999 top took to recover (in euros)",
        "• What the dollar did to euro investors in 2002, 2008 and 2025",
        "• Two AI-crash scenarios applied to today's index weights",
        "• What actually protected European investors, and the €37,219 price of panic",
        "",
        "⏱ Chapters",
        *[f"{a} {b}" for a, b in chapters],
        "",
        "📊 Data & sources",
        "• MSCI World Net (EUR), annual returns 2000–2025 + 2026 YTD to 31 Aug, 0.2% yearly fee",
        "• ECB Blog: “The AI boom: rational enthusiasm or the next dot-com bubble?” (Aug 2026)",
        "• Shiller CAPE (Sep 2026), S&P 500 top-10 concentration, MSCI World country weights (Aug 2026)",
        "• ECB euro reference rates, Euro area HICP, ECB monetary policy decision (10 Sep 2026)",
        "• ETFGI European ETF industry report (Aug 2026), justETF index comparisons",
        "• Monthly-plan figures approximated from annual returns (mid-year contributions)",
        "",
        "▶ Full video: The 4% Rule in Europe: I Simulated 10,000 Retirements",
        "",
        "This video is for education only and is not financial advice. Past performance does not guarantee future results.",
        "",
        "#AIBubble #MSCIWorld #ETF #EuropeanInvestor #StockMarketCrash",
    ]
    return "\n".join(lines), chapters


def thumbnail(path):
    img = E.background().copy()
    d = ImageDraw.Draw(img)
    top = E.rich_text("AI = {a:2000}?", 190, "grotesk", 700, "white", maxw=1800)
    img.paste(top, ((E.W - top.width) // 2, 70), top)
    big = E.build_sprite(dict(kind="big", text="€10k → €5.5k", color="red", size=170))
    img.paste(big, ((E.W - big.width) // 2, 330), big)
    ch = E.chart_sprite(dict(kind="chart", series=[dict(x=X, y=WORLD, upto=2002.0, color="amber", end_label=False)],
                             xr=(1999, 2003), yr=(4500, 10500), xticks=[], yticks=[], ref=10000, h=330))
    img.paste(ch, ((E.W - ch.width) // 2, 640), ch)
    d.rectangle((0, 0, E.W, 12), fill=E.C["amber"])
    img.resize((1280, 720), Image.LANCZOS).save(path, quality=92)


def main():
    os.makedirs(OUT, exist_ok=True)
    tl = json.load(open(os.path.join(HERE, "build", "timeline.json")))
    desc, chapters = description(tl)
    md = [f"# {TITLE}", "", f"Duration: {ts(tl['total'])}", "", "## Alternative titles (A/B)",
          *[f"- {t}" for t in ALT_TITLES], "", "## Description", "", "```", desc, "```", "",
          "## Tags", "", ", ".join(TAGS), ""]
    open(os.path.join(OUT, "youtube_metadata.md"), "w").write("\n".join(md))
    thumbnail(os.path.join(OUT, "thumbnail.jpg"))
    print("\n".join(f"{a} {b}" for a, b in chapters))


if __name__ == "__main__":
    main()
