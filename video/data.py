"""Datasets used in the video. Annual total returns, in EUR, net dividends.

MSCI World (net, EUR): derived from MSCI World net USD annual returns and
year-end EUR/USD (ECB reference rates). Cross-checked against MSCI's own EUR
factsheet for 2019-2022 (30.02 / 6.33 / 31.07 / -12.78). 2026 = YTD to 31 Aug
2026 (+14.35%, MSCI World Net EUR).
"""

YEARS = list(range(2000, 2027))

MSCI_WORLD_EUR = {
    2000: -6.1, 2001: -12.2, 2002: -32.7, 2003: 10.5, 2004: 6.4, 2005: 26.4,
    2006: 7.6, 2007: -2.5, 2008: -37.3, 2009: 25.6, 2010: 20.5, 2011: -2.4,
    2012: 13.6, 2013: 21.2, 2014: 19.2, 2015: 10.4, 2016: 11.0, 2017: 7.5,
    2018: -4.4, 2019: 30.0, 2020: 6.3, 2021: 31.1, 2022: -12.8, 2023: 19.6,
    2024: 26.6, 2025: 7.2, 2026: 14.35,
}

# Euro government bonds, all maturities (index level, approximate).
EURO_GOV_BONDS = {
    2000: 7.4, 2001: 5.8, 2002: 9.4, 2003: 4.0, 2004: 7.6, 2005: 5.4,
    2006: -0.3, 2007: 1.9, 2008: 9.1, 2009: 4.4, 2010: 1.1, 2011: 3.4,
    2012: 11.2, 2013: 2.2, 2014: 13.1, 2015: 1.7, 2016: 3.2, 2017: 0.2,
    2018: 1.0, 2019: 6.8, 2020: 5.0, 2021: -3.4, 2022: -18.4, 2023: 7.1,
    2024: 1.8, 2025: 0.6, 2026: -1.0,
}

FEE = 0.002  # 0.2% yearly ETF cost, same convention as the channel's shorts
YTD_FRACTION_2026 = 8 / 12


def growth(series, year, fee=FEE):
    f = YTD_FRACTION_2026 if year == 2026 else 1.0
    return (1 + series[year] / 100) * (1 - fee) ** f


def lump_sum_path(series, start_value=10_000, start=2000, end=2026, fee=FEE):
    """Year-end values; index 0 is the start (31 Dec of start-1)."""
    vals = [start_value]
    for y in range(start, end + 1):
        vals.append(vals[-1] * growth(series, y, fee))
    return vals


def monthly_plan(series, monthly=300, start=2000, end=2026, fee=FEE):
    """Approximation with annual data: each year's contributions are assumed
    to earn half of that year's return (mid-year convention)."""
    value, paid, path = 0.0, 0.0, []
    for y in range(start, end + 1):
        months = 8 if y == 2026 else 12
        g = growth(series, y, fee)
        value = value * g + monthly * months * g ** 0.5
        paid += monthly * months
        path.append((y, value, paid))
    return path


def mix(a, b, wa):
    return {y: wa * a[y] + (1 - wa) * b[y] for y in a}


if __name__ == "__main__":
    p = lump_sum_path(MSCI_WORLD_EUR)
    for y, v in zip([1999] + YEARS, p):
        print(y, round(v))
    rec = next(y for y, v in zip([1999] + YEARS, p) if y > 1999 and v >= 10_000)
    print("recovered (year-end) in", rec)
    print("plan 2001:", monthly_plan(MSCI_WORLD_EUR, start=2001)[-1])
    print("plan 2000:", monthly_plan(MSCI_WORLD_EUR, start=2000)[-1])
    b = lump_sum_path(EURO_GOV_BONDS, fee=0.0015)
    print("bonds 2000-2002:", round(b[3]))
    m = lump_sum_path(mix(MSCI_WORLD_EUR, EURO_GOV_BONDS, 0.6), fee=0.002)
    print("60/40 path:", [round(x) for x in m])
