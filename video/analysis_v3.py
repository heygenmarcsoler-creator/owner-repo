"""All numbers for the 30-minute v3 video, computed from data.py. Writes build/v3_numbers.json."""
import json
import os
import random
import statistics as st

from data import MSCI_WORLD_EUR as W, EURO_GOV_BONDS as B, MSCI_WORLD_USD as WU, FEE, lump_sum_path, mix, monthly_plan

FULL = list(range(2000, 2026))           # complete calendar years
R = {y: (1 + W[y] / 100) * (1 - FEE) for y in FULL}
RB = {y: (1 + B[y] / 100) * (1 - 0.0015) for y in FULL}
out = {}

# ---- heatmap: start at end of year s-1, hold h years -> total % change
heat = {}
for s in range(2000, 2017):
    row = []
    for h in range(1, 11):
        if s + h - 1 > 2025:
            row.append(None); continue
        v = 1.0
        for y in range(s, s + h):
            v *= R[y]
        row.append(round((v - 1) * 100, 1))
    heat[s] = row
out["heatmap"] = heat
cells = [c for r in heat.values() for c in r if c is not None]
out["heat_cells"] = len(cells)
out["heat_negative"] = sum(1 for c in cells if c < 0)
ten = [heat[s][9] for s in heat if heat[s][9] is not None]
out["ten_year_windows"] = len(ten)
out["ten_year_negative"] = sum(1 for c in ten if c < 0)
out["ten_year_worst"] = min(ten)
out["ten_year_best"] = max(ten)
out["ten_year_worst_start"] = [s for s in heat if heat[s][9] == min(ten)][0]
five = [heat[s][4] for s in heat if heat[s][4] is not None]
out["five_year_negative"] = sum(1 for c in five if c < 0)
out["five_year_windows"] = len(five)

# ---- drawdowns of the lump sum (year-end)
p = lump_sum_path(W)
peak, mdd = p[0], 0
for v in p:
    peak = max(peak, v); mdd = min(mdd, v / peak - 1)
out["lump_path"] = [round(v) for v in p]
out["lump_mdd_yearend"] = round(mdd * 100, 1)

# ---- portfolios 100/0, 80/20, 60/40 from end-1999
def path_mix(w):
    vals = [10000.0]
    for y in list(range(2000, 2026)) + [2026]:
        f = 8 / 12 if y == 2026 else 1
        g = (1 + (w * W[y] + (1 - w) * B[y]) / 100) * (1 - FEE) ** f
        vals.append(vals[-1] * g)
    return vals
for w in (1.0, 0.8, 0.6):
    v = path_mix(w)
    yrs = [1999] + list(range(2000, 2027))
    peak, dd = v[0], 0
    for x in v:
        peak = max(peak, x); dd = min(dd, x / peak - 1)
    rec = next((y for y, x in zip(yrs[1:], v[1:]) if x >= 10000 and y > 2002), None)
    out[f"mix_{int(w*100)}"] = dict(final=round(v[-1]), worst=round(min(v[1:15])), mdd=round(dd * 100, 1),
                                     back_above_10k=rec, path=[round(x) for x in v])

# ---- currency: cumulative 2000-2025, USD vs EUR
cu = ce = 1.0
for y in FULL:
    cu *= 1 + WU[y] / 100; ce *= 1 + W[y] / 100
out["cum_usd_2000_2025"] = round((cu - 1) * 100); out["cum_eur_2000_2025"] = round((ce - 1) * 100)
cu = ce = 1.0
for y in range(2000, 2003):
    cu *= 1 + WU[y] / 100; ce *= 1 + W[y] / 100
out["crash_2000_02_usd"] = round((cu - 1) * 100, 1); out["crash_2000_02_eur"] = round((ce - 1) * 100, 1)

# ---- panic variants (from end-1999, €10,000)
def value_after(y0, y1, v):
    for y in range(y0, y1 + 1):
        f = 8 / 12 if y == 2026 else 1
        v *= (1 + W[y] / 100) * (1 - FEE) ** f
    return v
cash = 1.02
end_02 = p[3]
v_cash = end_02 * cash ** (23 + 8 / 12)
v_reenter_06 = value_after(2007, 2026, end_02 * cash ** 4)          # back in at end-2006
v_reenter_13 = value_after(2014, 2026, end_02 * cash ** 11)         # back in after the recovery
end_08 = p[9]
v_sell08_reenter13 = value_after(2014, 2026, end_08 * cash ** 5)
out["panic"] = dict(stay=round(p[-1]), sold02_cash=round(v_cash), sold02_back06=round(v_reenter_06),
                    sold02_back13=round(v_reenter_13), sold08_back13=round(v_sell08_reenter13))

# ---- monthly plan: kept going vs stopped in 2008 (no new money 2009-2013, restart 2014)
def plan(stop=None):
    value, paid = 0.0, 0.0
    for y in list(range(2000, 2026)) + [2026]:
        months = 8 if y == 2026 else 12
        if stop and stop[0] <= y <= stop[1]:
            months = 0
        g = (1 + W[y] / 100) * (1 - FEE) ** (8 / 12 if y == 2026 else 1)
        value = value * g + 300 * months * g ** 0.5
        paid += 300 * months
    return round(value), round(paid)
out["plan_kept"] = plan()
out["plan_paused_2009_2013"] = plan((2009, 2013))

# ---- Monte Carlo: 10,000 x 20-year futures, 3-year block bootstrap of 2000-2025 (real order kept inside blocks)
rnd = random.Random(2026)
years = FULL
blocks = [years[i:i + 3] for i in range(len(years) - 2)]
def future(n=20, crash_first=False):
    seq = [2000, 2001, 2002] if crash_first else []
    while len(seq) < n:
        seq += rnd.choice(blocks)
    seq = seq[:n]
    v, path = 10000.0, [10000.0]
    for y in seq:
        v *= R[y]; path.append(v)
    return path
def summarise(paths):
    finals = sorted(x[-1] for x in paths)
    q = lambda a: finals[int(a * (len(finals) - 1))]
    under = {h: round(100 * sum(1 for x in paths if x[h] < 10000) / len(paths), 1) for h in (1, 5, 10, 15, 20)}
    pct = {k: [round(sorted(x[t] for x in paths)[int(k / 100 * (len(paths) - 1))]) for t in range(21)] for k in (5, 25, 50, 75, 95)}
    return dict(p5=round(q(0.05)), p50=round(q(0.5)), p95=round(q(0.95)), under=under, bands=pct)
mc = [future() for _ in range(10000)]
out["mc"] = summarise(mc)
mc_crash = [future(crash_first=True) for _ in range(10000)]
out["mc_crash"] = summarise(mc_crash)
# years to recover in crash-first futures
rec = []
for x in mc_crash:
    t = next((i for i in range(4, 21) if x[i] >= 10000), None)
    rec.append(t if t is not None else 99)
out["mc_crash_recover_median_years"] = st.median(rec)
out["mc_crash_not_recovered_20y_pct"] = round(100 * sum(1 for t in rec if t == 99) / len(rec), 1)
out["mc_crash_recovered_within_10y_pct"] = round(100 * sum(1 for t in rec if t <= 10) / len(rec), 1)

os.makedirs("build", exist_ok=True)
json.dump(out, open("build/v3_numbers.json", "w"), indent=1)
show = {k: v for k, v in out.items() if k not in ("heatmap",) and not (isinstance(v, dict) and "path" in v)}
for k, v in show.items():
    if isinstance(v, dict) and "bands" in v:
        v = {kk: vv for kk, vv in v.items() if kk != "bands"}
    print(k, v)
for w in (100, 80, 60):
    d = out[f"mix_{w}"]; print(w, {k: v for k, v in d.items() if k != "path"})
print("heat 2000:", heat[2000]); print("heat 2008:", heat[2008]); print("heat 2009:", heat[2009])

# ---- extra numbers (v3 long version)
ex = {}
cols = list(zip(*[heat[s] for s in heat]))
ex["loss_prob_by_horizon"] = [round(100 * sum(1 for c in col if c is not None and c < 0) / sum(1 for c in col if c is not None), 1) for col in cols]
ex["windows_by_horizon"] = [sum(1 for c in col if c is not None) for col in cols]
# lump sum of the same €96,000 at the end of 1999 vs the monthly plan
ex["lump_96k_today"] = round(96000 * p[-1] / 10000)
# monthly plan Monte Carlo: €300/month for 20 years, normal vs crash-first futures
def plan_future(crash_first):
    seq = [2000, 2001, 2002] if crash_first else []
    while len(seq) < 20:
        seq += rnd.choice(blocks)
    v = 0.0
    for y in seq[:20]:
        v = v * R[y] + 3600 * R[y] ** 0.5
    return v
pn = sorted(plan_future(False) for _ in range(10000))
pc = sorted(plan_future(True) for _ in range(10000))
q = lambda a, s: round(s[int(a * (len(s) - 1))])
ex["plan_mc_normal"] = dict(p5=q(0.05, pn), p50=q(0.5, pn), p95=q(0.95, pn), below_paid=round(100 * sum(1 for v in pn if v < 72000) / len(pn), 1))
ex["plan_mc_crash"] = dict(p5=q(0.05, pc), p50=q(0.5, pc), p95=q(0.95, pc), below_paid=round(100 * sum(1 for v in pc if v < 72000) / len(pc), 1))
# crash anatomy (annual EUR, peak-to-trough on year-end values, years down)
ex["anatomy"] = {"2000-2002": dict(years_down=3, fall=round((p[3] / p[0] - 1) * 100, 1)),
                 "2008": dict(years_down=1, fall=round(W[2008], 1)),
                 "2022": dict(years_down=1, fall=round(W[2022], 1))}
out.update(ex)
json.dump(out, open("build/v3_numbers.json", "w"), indent=1)
print("EXTRA", ex)
dbl = {}
for name, paths in (("normal", mc), ("crash", mc_crash)):
    dbl[name] = {h: round(100 * sum(1 for x in paths if x[h] >= 20000) / len(paths), 1) for h in (10, 20)}
out["double"] = dbl
json.dump(out, open("build/v3_numbers.json", "w"), indent=1)
print("DOUBLE", dbl)
