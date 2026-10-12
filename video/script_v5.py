"""v5 (channel format, ~8 min): "Trump vs the market" - six forces moving a world ETF in October 2026.

Same scene DSL as script_v3: S(text, *elements, k=kicker, t=headline, src=source, chunk=True on the
first segment of each TTS request). '@x' in the text marks the word where elements with at='x' appear.
All figures are sourced in the description (research notes in research/v5_trump_market.md).
"""


def S(text, *elements, k=None, t=None, src=None, chunk=False, cam=None):
    return dict(text=text, elements=list(elements), kicker=k, title=t, src=src, chunk=chunk, cam=cam)


def E(kind, **kw):
    kw["kind"] = kind
    return kw


def cnt(to, fmt, color="amber", size=210, frm=0, label=None, **k):
    return E("cnt", to=to, fmt=fmt, color=color, size=size, frm=frm, label=label, **k)
def statement(text, size=72, **k): return E("statement", text=text, size=size, **k)
def note(text, **k): return E("note", text=text, **k)
def cards(items, **k): return E("cards", items=items, **k)
def rows(items, **k): return E("rows", items=items, **k)
def bars(items, maxv=None, **k): return E("bars", items=items, maxv=maxv, **k)
def vbars(items, maxv=None, **k): return E("vbars", items=items, maxv=maxv, **k)
def line(series, **k): return E("line", series=series, **k)
def donut(value, label, color="amber", **k): return E("donut", value=value, label=label, color=color, **k)
def chips(items, **k): return E("chips", items=items, **k)
def table(header, items, **k): return E("table", header=header, items=items, **k)
def timeline(items, **k): return E("timeline", items=items, **k)
def takeaways(items, **k): return E("takeaways", items=items, **k)
def endcard(label, title, **k): return E("endcard", label=label, title=title, **k)
def ser(x, y, color="amber", label=None, upto=None, frm=None, dash=False):
    return dict(x=x, y=y, color=color, label=label, upto=upto if upto is not None else x[-1], frm=frm, dash=dash)


# --------------------------------------------------------------------------- data
# Fed funds target range, upper bound (FOMC decisions): hikes 2022-23, six cuts 2024-25, hike 16 Sep 2026
_FED = [(2021.9, 0.25), (2022.21, 0.50), (2022.34, 1.00), (2022.46, 1.75), (2022.57, 2.50), (2022.72, 3.25),
        (2022.84, 4.00), (2022.96, 4.50), (2023.09, 4.75), (2023.21, 5.00), (2023.34, 5.25), (2023.57, 5.50),
        (2024.71, 5.00), (2024.85, 4.75), (2024.96, 4.50), (2025.71, 4.25), (2025.83, 4.00), (2025.94, 3.75),
        (2026.71, 4.00)]
FED_X, FED_Y = [_FED[0][0]], [_FED[0][1]]
for (x, y) in _FED[1:]:
    FED_X += [x, x + 0.001]
    FED_Y += [FED_Y[-1], y]
FED_X.append(2026.78)
FED_Y.append(4.00)
FED_AX = dict(xr=(2021.9, 2026.9), yr=(0, 6), xticks=[2022, 2023, 2024, 2025, 2026],
              yticks=[(1, "1%"), (2, "2%"), (3, "3%"), (4, "4%"), (5, "5%")], ref=1.0, fmt="{:.2f}%")

# EUR/USD, selected 2026 dates (ECB / market quotes)
FX_X = [2026.0, 2026.07, 2026.25, 2026.48, 2026.58, 2026.69, 2026.78]
FX_Y = [1.174, 1.202, 1.150, 1.136, 1.154, 1.163, 1.120]
FX_AX = dict(xr=(2026.0, 2026.85), yr=(1.08, 1.22), xticks=[(2026.0, "Jan"), (2026.25, "Apr"), (2026.5, "Jul"),
                                                          (2026.75, "Oct")],
             yticks=[(1.10, "$1.10"), (1.15, "$1.15"), (1.20, "$1.20")], ref=1.174, fmt="${:.2f}")

K0 = "TRUMP VS THE MARKET"
K1, K2, K3 = "1 · TRUMP VS THE FED", "2 · THE OIL SHOCK", "3 · THE BOND ALARM"
K4, K5, K6 = "4 · THE AI MARKET", "5 · TARIFFS & THE DOLLAR", "6 · THE MIDTERMS"
K7, K8 = "WHAT IT MEANS FOR YOUR ETF", "THE VERDICT"

SRC_FED = "Source: Federal Reserve (FOMC decisions); Trump on Truth Social, 16 September 2026"
SRC_CPI = "Source: US Bureau of Labor Statistics, CPI August 2026 (released 11 September)"
SRC_OIL = "Sources: ICE Brent futures settlements; Trading Economics; EIA Short-Term Energy Outlook (August 2026)"
SRC_EZ = "Source: Eurostat flash estimate, September 2026; ECB key interest rates"
SRC_10Y = "Source: US Treasury 10-year yield, Bloomberg/CNBC; 7 October 2026 = highest since April 2002"
SRC_CBO = "Source: Congressional Budget Office, fiscal year 2026 projections"
SRC_SPX = "Source: S&P 500 closes (LSEG); record 7,844.52, week of 5 October 2026"
SRC_TAR = "Source: Yale Budget Lab, State of U.S. Tariffs (Jan 2025, Mar 2026, Apr 2026)"
SRC_FX = "Source: ECB euro reference rates and market quotes, selected 2026 dates"
SRC_MID = "Sources: Carson Investment Research (FactSet) since 1950; CFRA since 1946; prediction markets, early October"

SIX = ["Trump vs the Fed", "The oil shock", "The bond alarm", "The AI market", "Tariffs & the dollar", "The midterms"]

SEGMENTS = [
    # =========================================================== HOOK (chunk 0)
    S("On the sixteenth of September, twelve days after Donald Trump demanded a rate cut, the Federal Reserve raised rates instead.",
      cards([("Trump, 4 September", "CUT", "demands lower rates", "red"), ("The Fed, 16 September", "+0.25%", "first hike since 2023", "amber")]),
      k=K0, t="He asked for a cut. He got a hike.", src=SRC_FED, chunk=True),
    S("Hours later, he asked for one percent. @a Or less.",
      cnt(1, "{:.0f}%", color="red", size=240, label="Trump's demand for the Fed's rate", frm=4), note("“…or less.”", at="a"),
      k=K0, t="His answer: 1%", src=SRC_FED),
    S("Since then, the ten-year US Treasury yield has hit five point three five percent, the highest since 2002.",
      cnt(5.35, "{:.2f}%", color="red", size=230, label="US 10-year Treasury yield · 7 October 2026 · highest since April 2002"),
      k=K0, t="Bond yields at a 24-year high", src=SRC_10Y),
    S("Oil is above one hundred dollars. @a Inflation in the euro area just jumped to three point eight percent.",
      cards([("Brent crude, 9 October", "$104.72", "per barrel", "red")]),
      cards([("Euro area inflation", "3.8%", "September, highest since 2023", "red")], at="a"),
      k=K0, t="Oil > $100, inflation 3.8%", src="Sources: ICE Brent settlement 9 Oct 2026; Eurostat flash, September 2026"),
    S("And yet the S and P five hundred just set a record.",
      cnt(7844, "{:,.0f}", color="green", size=230, label="S&P 500 record high · week of 5 October 2026"),
      k=K0, t="…and stocks at a record", src=SRC_SPX),
    S("Something has to give. So here are six forces moving markets right now, the numbers behind each, and what they mean if you own a world ETF in euros.",
      chips(SIX), k=K0, t="Six forces, one portfolio"),

    # =========================================================== 1 · TRUMP VS THE FED
    S("Force one: Trump versus the Fed. In 2022 and 2023, the Fed took its rate from almost zero to five and a half percent.",
      line([ser(FED_X, FED_Y, "amber", "Fed funds (upper)", upto=2023.6)], draw="s", **FED_AX),
      k=K1, t="The Fed's rate since 2022", src=SRC_FED),
    S("Then it cut six times, down to three point seven five by December 2025.",
      line([ser(FED_X, FED_Y, "amber", "Fed funds (upper)", upto=2025.95, frm=2023.6)], draw="s", **FED_AX),
      k=K1, t="Six cuts to 3.75%", src=SRC_FED),
    S("In May 2026, Kevin Warsh, the chair Trump picked, took over. @a His first move was a hike, to four percent.",
      line([ser(FED_X, FED_Y, "amber", "Fed funds (upper)", upto=2026.78, frm=2025.95)], draw="a", **FED_AX),
      note("Dashed line: Trump's demand, 1% or less"), k=K1, t="Warsh's first move: a hike", src=SRC_FED),
    S("Why? Inflation. US prices rose more than four percent a year this spring, @a and three point four percent in August.",
      vbars([("Spring", 4.2, "≈4.2%", "red"), ("August", 3.4, "3.4%", "amber"), ("Target", 2.0, "2%", "slate")], maxv=5,
            steps=[None, "a", "a"]), k=K1, t="US inflation, year on year", src=SRC_CPI),
    S("But look inside. Core inflation, without food and energy, is two point four percent, the lowest since 2021. @a Gasoline is up twenty-seven percent.",
      cards([("Core inflation", "2.4%", "lowest since March 2021", "green")]),
      cards([("Gasoline prices", "+27.4%", "year on year, August", "red")], at="a"), k=K1, t="An energy shock, not a boom", src=SRC_CPI),
    S("This is an oil shock, not an overheating economy. And the Fed is fighting it anyway.",
      statement("An oil shock, not an overheating economy.", size=70), k=K1),
    S("Markets now price an eighty-six percent chance of another hike in December.",
      donut(86, "chance of another Fed hike in December · CME FedWatch, early October", color="red"),
      k=K1, t="More hikes priced in", src="Source: CME FedWatch, early October 2026"),
    S("He has also threatened to cut off trade with countries that run surpluses with the US, if the Fed doesn't cut.",
      statement("No cut? Then no trade with surplus countries.", size=66), note("Trump's threat, September 2026"),
      k=K1, t="Pressure on the Fed", src="Sources: 24/7 Wall St; Shafaq News, 17 September 2026"),
    S("Trump wants one percent. @a The market expects more than four. That gap is the first force on this list.",
      bars([("Trump's demand", 1, "1%", "slate")], maxv=5), bars([("Fed now", 4.0, "3.75–4.00%", "amber"), ("Priced for December", 4.25, "≈4.25%", "red")], maxv=5, at="a"),
      k=K1, t="The gap", src="Sources: Truth Social; Federal Reserve; CME FedWatch"),

    # =========================================================== 2 · THE OIL SHOCK
    S("Force two: oil. On the twenty-eighth of February, the US and Israel struck Iran. @a Days later, the Strait of Hormuz was closed.",
      timeline([("28 Feb", "war begins", "red"), ("early Mar", "Hormuz closed", "red"), ("8 Apr", "ceasefire", "green"), ("Jul", "attacks again", "red")]),
      k=K2, t="2026: war and Hormuz", src="Sources: Reuters, Al Jazeera, CNBC, 2026", chunk=True),
    S("Brent crude started at about seventy-two dollars. @a March was its biggest monthly jump since records began in 1988, more than sixty percent.",
      vbars([("Pre-war", 72, "≈$72", "slate")], maxv=120), note("March 2026: +60%, the biggest monthly jump since 1988", at="a"),
      k=K2, t="Brent crude, $ per barrel", src=SRC_OIL),
    S("A ceasefire in April brought it back below one hundred. @a By mid-July it was under eighty. @b Then the attacks resumed.",
      vbars([("Pre-war", 72, "≈$72", "slate"), ("10 Apr", 96, "≈$96", "amber"), ("13 Jul", 78.8, "$79", "amber"),
             ("9 Oct", 104.7, "$104.72", "red")], maxv=120, steps=[None, None, "a", "b"]),
      k=K2, t="Brent crude, $ per barrel", src=SRC_OIL),
    S("On the ninth of October, Brent settled at one hundred and four dollars seventy-two. Hormuz is carrying roughly half its pre-war flow.",
      cards([("Brent, 9 October", "$104.72", "settlement price", "red"), ("Oil through Hormuz", "≈½", "of its pre-war flow", "amber")]),
      k=K2, t="Where we are now", src=SRC_OIL),
    S("For Europe this hurts more than for America. Euro area energy inflation hit eighteen point eight percent in September.",
      cnt(18.8, "{:.1f}%", color="red", size=230, label="euro area energy inflation · September 2026 flash"), k=K2, t="Europe pays more", src=SRC_EZ),
    S("Headline inflation is three point eight percent, the highest since 2023. @a The E C B has already raised rates twice this year, to two and a half percent.",
      cards([("Euro area inflation", "3.8%", "September flash", "red")]),
      cards([("ECB deposit rate", "2.50%", "hikes in June and September", "amber")], at="a"), k=K2, t="The ECB is hiking too", src=SRC_EZ),
    S("Trump says there will be no attack on Iran before the midterms, and he has lined up Russian diesel to cool fuel prices.",
      rows([("No US attack on Iran before the midterms", "pledge", "amber"), ("Russian diesel for the US market", "deal", "amber")]),
      k=K2, t="Trump's oil moves", src="Sources: Bloomberg, Reuters, October 2026"),
    S("The US energy agency expects Brent to average sixty-nine dollars in 2027, if production in the Gulf recovers.",
      bars([("Brent now", 104.7, "$105", "red"), ("EIA forecast, 2027 average", 69, "$69", "green")], maxv=120),
      k=K2, t="The way out", src=SRC_OIL),

    # =========================================================== 3 · THE BOND ALARM (chunk 1)
    S("Force three, and the one I'd watch most: bond yields. The ten-year Treasury started the year around four point two percent, and briefly dipped below four in February.",
      vbars([("Jan 2026", 4.2, "≈4.2%", "slate"), ("Feb", 3.95, "<4%", "slate")], maxv=6),
      k=K3, t="US 10-year yield, 2026", src=SRC_10Y),
    S("@a It passed four and a half in May, @b and hit five point three five on the seventh of October. The highest since April 2002.",
      vbars([("Jan 2026", 4.2, "≈4.2%", "slate"), ("Feb", 3.95, "<4%", "slate"), ("May", 4.5, "4.5%", "amber"),
             ("7 Oct", 5.35, "5.35%", "red")], maxv=6, steps=[None, None, "a", "b"]),
      k=K3, t="US 10-year yield, 2026", src=SRC_10Y),
    S("Why it matters: Washington will pay about one trillion dollars in interest this year. @a The deficit is about one point nine trillion.",
      cards([("Interest on US debt", "$1.0T", "fiscal 2026 · 3.3% of GDP", "red")]),
      cards([("US budget deficit", "$1.9T", "fiscal 2026 · 5.8% of GDP", "red")], at="a"), k=K3, t="The cost of 5% yields", src=SRC_CBO),
    S("It also makes stocks look expensive. Based on ten-year average earnings, the S and P five hundred earns about two point four percent of its price.",
      bars([("S&P 500 earnings yield", 2.4, "2.4%", "amber")], maxv=6),
      k=K3, t="Stocks vs bonds", src="Calculation: 1 ÷ Shiller CAPE (≈41, September 2026)"),
    S("@a A ten-year Treasury pays five point three five. That's the biggest gap in favour of bonds since the dot-com era.",
      bars([("S&P 500 earnings yield", 2.4, "2.4%", "amber")], maxv=6),
      bars([("US 10-year Treasury", 5.35, "5.35%", "red")], maxv=6, at="a"),
      note("Gap ≈ −2.9 points: wider than in 2007 or 2023"), k=K3, t="Stocks vs bonds",
      src="Calculation: 1 ÷ CAPE vs 10-year yield; 2000 ≈ −3.9, 2007 ≈ −1.0, 2023 ≈ −1.7 points"),
    S("Even gold noticed. It closed at a record five thousand three hundred and eighteen dollars in January. @a Today it's about twenty-two percent lower, because high yields make a metal that pays nothing less attractive.",
      cards([("Gold record close, 29 January", "$5,318", "per ounce", "amber")]),
      cards([("Gold, early October", "≈$4,150", "−22% from the record", "red")], at="a"), k=K3, t="Gold: −22% from the top",
      src="Sources: COMEX gold futures; CNBC, October 2026"),

    # =========================================================== 4 · THE AI MARKET
    S("Force four: the AI market. The S and P five hundred closed 2025 at six thousand eight hundred and forty-six. @a Last week it hit seven thousand eight hundred and forty-four. Almost fifteen percent higher.",
      bars([("31 Dec 2025", 6845.5, "6,846", "slate")], maxv=8200), bars([("Record, Oct 2026", 7844.5, "7,844 (+14.6%)", "green")], maxv=8200, at="a"),
      k=K4, t="S&P 500 in 2026", src=SRC_SPX),
    S("It fell about eight percent when the war began, @a and was back at a record by the fifteenth of April.",
      cards([("28 Feb → 30 Mar", "−8%", "the war sell-off", "red")]),
      cards([("15 April", "Record", "all losses recovered", "green")], at="a"), k=K4, t="The war dip lasted 7 weeks",
      src="Sources: LSEG, CNN, CNBC, April 2026"),
    S("Most of the gains come from a handful of AI giants. The ten largest companies are close to forty percent of the index.",
      donut(40, "of the S&P 500 is in its 10 largest companies", color="amber"), k=K4, t="Ten companies, 40%",
      src="Source: S&P 500 concentration data, 2026"),
    S("Nvidia alone is valued at around five point three trillion dollars, more than every listed company in Germany combined.",
      cnt(5.3, "${:.1f}T", color="amber", size=230, label="Nvidia market value · one company"), k=K4, t="One company > all of Germany",
      src="Source: market capitalisation data, September 2026"),
    S("Even the president's account is in on it. His filings show ninety-four trades in the Magnificent Seven in the first quarter alone, @a worth fifty to seventy million dollars.",
      cards([("Trades in the Magnificent 7", "94", "Q1 2026 · Trump's account", "amber")]),
      cards([("Value", "$50–70M", "disclosed ranges", "amber")], at="a"),
      note("White House: the portfolio is managed by third parties"), k=K4, t="The president's portfolio",
      src="Source: Office of Government Ethics filings, via Yahoo Finance and SCMP"),
    S("So a world ETF today is, to a large extent, a bet on AI. And on the dollar.",
      statement("A world ETF today: a bet on AI, and on the dollar.", size=66), k=K4),

    # =========================================================== 5 · TARIFFS & THE DOLLAR
    S("Force five: tariffs and the dollar. In February, the US Supreme Court struck down Trump's emergency tariffs.",
      statement("February 2026: the Supreme Court strikes down the emergency tariffs.", size=60), k=K5, t="Tariffs, round two", chunk=True),
    S("The average effective US tariff rate fell from fourteen point three percent to ten and a half, @a then climbed back to almost twelve in April. Before 2025 it was about two and a half.",
      vbars([("Jan 2025", 2.4, "2.4%", "slate"), ("Pre-ruling", 14.3, "14.3%", "red"), ("Mar 2026", 10.5, "10.5%", "amber"),
             ("Apr 2026", 11.8, "11.8%", "red")], maxv=16, steps=[None, None, None, "a"]),
      k=K5, t="Average effective US tariff rate", src=SRC_TAR),
    S("A temporary global surcharge that replaced them expired on the twenty-fourth of July. Tariffs now come sector by sector.",
      timeline([("Feb", "ruling", "amber"), ("24 Feb", "10% surcharge", "red"), ("24 Jul", "expired", "green"), ("now", "sector tariffs", "amber")]),
      k=K5, t="A moving target", src="Sources: Yale Budget Lab; US trade notices, 2026"),
    S("For you, the bigger story is the currency. In 2025 the euro rose thirteen percent against the dollar. @a World stocks gained twenty-one percent in dollars, but only seven in euros.",
      cards([("EUR/USD in 2025", "+13%", "1.039 → 1.174", "blue")]),
      bars([("MSCI World 2025, in USD", 21, "+21%", "slate"), ("MSCI World 2025, in EUR", 7.2, "+7.2%", "amber")], maxv=25, at="a"),
      k=K5, t="2025: the euro took two thirds", src="Sources: ECB reference rates; MSCI World net, USD and EUR"),
    S("This year it turned. The euro started the year at one seventeen, peaked just above one twenty in January, @a and is now around one twelve.",
      line([ser(FX_X, FX_Y, "blue", "EUR/USD")], draw="a", **FX_AX), k=K5, t="EUR/USD in 2026", src=SRC_FX),
    S("About seventy percent of a world ETF is priced in dollars, @a and the dollar is up almost five percent against the euro since January.",
      donut(71, "of a world ETF is priced in US dollars", color="blue"),
      cards([("Dollar vs euro, 2026", "+4.8%", "1 January → 12 October", "green")], at="a"), k=K5, t="The dollar helped you",
      src="Calculation: EUR/USD 1.174 → ≈1.12; MSCI World country weights"),
    S("In euros, the M S C I World was up fourteen percent this year to the end of August.",
      cnt(14.35, "+{:.1f}%", color="green", size=220, label="MSCI World net, in EUR · 1 January → 31 August 2026"),
      k=K5, t="Your world ETF in 2026", src="Source: MSCI World Net EUR index, end of August 2026"),
    S("The risk is the reverse. If Trump gets his rate cuts, the dollar would likely fall, and euro investors would give some of that back.",
      statement("Trump's rate cut could be your currency loss.", size=70), k=K5),

    # =========================================================== 6 · THE MIDTERMS
    S("Force six: the midterms, on the third of November. Prediction markets give the Democrats around eighty percent odds of winning the House. @a The Senate is a toss-up.",
      cards([("House", "≈81–85%", "Democrats win, market odds", "blue")]),
      cards([("Senate", "≈50/50", "toss-up", "slate")], at="a"), k=K6, t="3 November", src=SRC_MID),
    S("Midterm years are usually rough. Since 1950, the S and P five hundred has fallen seventeen and a half percent from peak to trough in the average midterm year, @a against eleven to thirteen in other years.",
      bars([("Average midterm year", 17.5, "−17.5%", "red")], maxv=20),
      bars([("Other years of the cycle", 12, "−11% to −13%", "slate")], maxv=20, at="a"),
      k=K6, t="Average peak-to-trough fall, since 1950", src=SRC_MID),
    S("This year, the worst fall so far was under ten percent, in March.",
      bars([("Average midterm year", 17.5, "−17.5%", "red"), ("Other years of the cycle", 12, "−11% to −13%", "slate"),
            ("2026 so far", 9, "< −10%", "amber")], maxv=20), k=K6, t="Average peak-to-trough fall, since 1950", src=SRC_MID),
    S("And here's the part people forget. In the twelve months after every midterm election since 1946, the S and P five hundred went up. @a On average, by about sixteen percent.",
      cards([("12 months after a midterm", "Always up", "every midterm since 1946", "green")]),
      cards([("Average gain", "≈+16%", "12 months after", "green")], at="a"), k=K6, t="After the vote", src=SRC_MID),
    S("That's history, not a promise. But it's one reason not to sell before an election.",
      statement("History, not a promise.", size=80), note("Selling before the vote has rarely paid"), k=K6),

    # =========================================================== WHAT IT MEANS
    S("So what does all this mean if you own a world ETF in euros? Three scenarios, not forecasts.",
      chips(["1 · Fed keeps hiking", "2 · Trump gets his cuts", "3 · Hormuz reopens"]), k=K7, t="Three scenarios"),
    S("One: the Fed keeps hiking and yields stay above five percent. @a Expensive stocks, especially the AI giants, are most at risk, while bonds and cash finally pay.",
      rows([("Fed keeps hiking", "yields > 5%", "red")]),
      rows([("AI giants", "most at risk", "red"), ("Bonds and cash", "pay more", "green")], at="a"), k=K7, t="Scenario 1"),
    S("Two: Trump gets his way and rates fall fast. @a Stocks may like it at first, but the dollar would likely weaken, and inflation could come back.",
      rows([("Rates fall fast", "Trump wins", "amber")]),
      rows([("Stocks", "relief rally", "green"), ("Dollar, for euro investors", "weaker", "red"), ("Inflation", "risk returns", "red")], at="a"),
      k=K7, t="Scenario 2"),
    S("Three: Hormuz reopens. @a Oil falls toward that sixty-nine dollar forecast, inflation cools, and both the Fed and the E C B can stop hiking.",
      rows([("Hormuz reopens", "oil → $69", "green")]),
      rows([("Inflation", "cools", "green"), ("Fed and ECB", "stop hiking", "green")], at="a"), k=K7, t="Scenario 3"),

    # =========================================================== VERDICT
    S("My takeaways, not advice.",
      takeaways(["It's an oil shock: watch Hormuz", "Bonds pay again", "70% of your ETF is in dollars", "Don't trade the midterms"]),
      k=K8, t="What I'd keep in mind"),
    S("@a One: this is an energy shock. Watch oil and the Strait of Hormuz more than every headline about the Fed.",
      takeaways(["It's an oil shock: watch Hormuz", "Bonds pay again", "70% of your ETF is in dollars", "Don't trade the midterms"], hl=0, at="a"),
      k=K8, t="What I'd keep in mind"),
    S("@a Two: bonds pay again. Five point three five percent in the US, around two and a half on euro cash and short bonds.",
      takeaways(["It's an oil shock: watch Hormuz", "Bonds pay again", "70% of your ETF is in dollars", "Don't trade the midterms"], hl=1, at="a"),
      k=K8, t="What I'd keep in mind"),
    S("@a Three: about seventy percent of your world ETF is in dollars. A rate cut that Trump celebrates could cost you on the currency.",
      takeaways(["It's an oil shock: watch Hormuz", "Bonds pay again", "70% of your ETF is in dollars", "Don't trade the midterms"], hl=2, at="a"),
      k=K8, t="What I'd keep in mind"),
    S("@a Four: since 1946, the year after a midterm has always ended higher. Selling before the vote has been the expensive move.",
      takeaways(["It's an oil shock: watch Hormuz", "Bonds pay again", "70% of your ETF is in dollars", "Don't trade the midterms"], hl=3, at="a"),
      k=K8, t="What I'd keep in mind"),
    S("Which of the six forces worries you most? Tell me in the comments. Sources are in the description, and this isn't financial advice.",
      chips(SIX), k=K8, t="Your turn"),
    S("Next video: the same fifty thousand euro portfolio, taxed in ten European countries. Subscribe so you don't miss it.",
      endcard("NEXT VIDEO", "The same €50,000 portfolio, taxed in 10 European countries"), k=K8),
]

CHUNK_STARTS = [i for i, s in enumerate(SEGMENTS) if s["chunk"]]
CHAPTERS = [(i, s["kicker"]) for i, s in enumerate(SEGMENTS) if i == 0 or s["kicker"] != SEGMENTS[i - 1]["kicker"]]
