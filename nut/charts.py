"""Render every dashboard chart with matplotlib (deterministic SVG + PNG)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

plt.rcParams.update(
    {
        "svg.hashsalt": "near-usage-thesis",
        "svg.fonttype": "none",
        "font.family": "DejaVu Sans",
        "font.size": 9.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "legend.frameon": False,
        "figure.dpi": 100,
    }
)

GREEN = "#00a86b"
NEAR_GREEN = "#00ec97"
ORANGE = "#e07b00"
GREY = "#8a8f98"
DARK = "#1f2328"
BLUE = "#2f6fdf"
PURPLE = "#8250df"
RED = "#cf222e"


def _save(fig, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{name}.svg", format="svg", bbox_inches="tight", metadata={"Date": None})
    svg = (out_dir / f"{name}.svg").read_text(encoding="utf-8")
    # browsers without DejaVu Sans would fall back to a serif font
    svg = svg.replace("font-family: 'DejaVu Sans'", "font-family: 'DejaVu Sans', 'Helvetica Neue', Arial, sans-serif")
    (out_dir / f"{name}.svg").write_text(svg, encoding="utf-8")
    fig.savefig(out_dir / f"{name}.png", format="png", dpi=130, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def _pct(ax, axis="y", digits=0):
    from matplotlib.ticker import FuncFormatter

    f = FuncFormatter(lambda v, _: f"{100 * v:.{digits}f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def _human(ax, axis="y", prefix=""):
    from matplotlib.ticker import FuncFormatter

    def h(v, _):
        a = abs(v)
        for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if a >= div:
                return f"{prefix}{v / div:g}{suf}"
        return f"{prefix}{v:g}"

    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(FuncFormatter(h))


def issuance(out, d, iss, samples, as_of):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True, gridspec_kw={"height_ratios": [1.1, 1]})
    s = d["total_supply_near"].loc[:as_of].dropna()
    a1.plot(s.index, s.values, color=DARK, lw=1.4, label="Total supply, NearBlocks indexer (daily)")
    a1.scatter(samples["time"], samples["total_supply_near"], s=9, color=NEAR_GREEN, edgecolor=GREEN, lw=0.5, zorder=3, label="Block-header total_supply, archival RPC (samples)")
    _human(a1)
    a1.set_ylabel("NEAR")
    a1.legend(loc="upper left")
    a1.set_title("NEAR total supply and gross issuance rate")
    r = iss["_gross_rate_7d"].loc["2020-11-01":as_of]
    a2.plot(r.index, r.values, color=GREEN, lw=1.0)
    _pct(a2, digits=1)
    a2.set_ylim(0, max(0.08, float(np.nanquantile(r.values, 0.995)) * 1.1))
    a2.set_ylabel("7-day gross issuance, annualized")
    if iss.get("halving_detected_on"):
        hd = pd.Timestamp(iss["halving_detected_on"])
        a2.axvline(hd, color=RED, lw=1, ls="--")
        a2.annotate(f"issuance cut detected {iss['halving_detected_on']}", (hd, 0.065), xytext=(-8, 0), textcoords="offset points", ha="right", color=RED, fontsize=9)
    a2.xaxis.set_major_locator(mdates.YearLocator())
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _save(fig, out, "issuance")


def epochs(out, ep):
    fig, ax = plt.subplots(figsize=(9, 3.8))
    x = ep["start"]
    w = (ep["duration_s"].median() / 86400) * 0.8
    ax.bar(x, ep["minted_near"], width=w, color=GREY, label="NEAR minted for the epoch")
    ax.bar(x, ep["burnt_near"], width=w, color=ORANGE, label="NEAR burnt during the epoch")
    _human(ax)
    ax.set_ylabel("NEAR per epoch")
    ax2 = ax.twinx()
    ax2.plot(x, ep["burnt_near"] / ep["minted_near"], color=RED, lw=1.2, label="burnt / minted (right axis)")
    _pct(ax2, digits=1)
    ax2.set_ylim(0, max(0.02, float((ep["burnt_near"] / ep["minted_near"]).max()) * 1.3))
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="center left", fontsize=8.5)
    ax.set_title("Per-epoch minting vs burning, measured from block headers")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    _save(fig, out, "epochs")


def capture_monthly(out, monthly):
    m = monthly.loc[monthly.index >= "2025-01"]
    fig, ax = plt.subplots(figsize=(9, 4.0))
    idx = np.arange(len(m))
    ax.bar(idx - 0.2, m["minted_near"], width=0.4, color=GREY, label="NEAR minted (issuance)")
    ax.bar(idx + 0.2, m["burn_near"], width=0.4, color=ORANGE, label="Gas burn")
    ax.bar(idx + 0.2, m["intents_revenue_near"], width=0.4, bottom=m["burn_near"], color=GREEN, label="NEAR Intents revenue, in NEAR")
    _human(ax)
    ax.set_ylabel("NEAR per month")
    ax.set_xticks(idx)
    ax.set_xticklabels([f"{p[2:4]}-{p[5:]}" + ("*" if not c else "") for p, c in zip(m.index, m["complete"])], rotation=90, fontsize=8)
    for i, (cov, c) in enumerate(zip(m["coverage_total"], m["complete"])):
        if c:
            ax.text(i + 0.2, (m["burn_near"].iloc[i] + m["intents_revenue_near"].iloc[i]) * 1.02 + m["minted_near"].max() * 0.01, f"{100 * cov:.0f}%", ha="center", fontsize=7.5, color=DARK)
    ax.legend(loc="upper right", fontsize=8.5)
    ax.set_title("Issuance vs usage-based value capture, by month (label = % of issuance offset)")
    ax.set_xlabel("year-month (* = month in progress)")
    _save(fig, out, "capture_monthly")


def coverage_official(out, table):
    fig, ax = plt.subplots(figsize=(9, 3.6))
    idx = np.arange(len(table))
    ax.plot(idx, table["ours"], marker="o", color=GREEN, lw=1.6, label="This repo: (gas burn + Intents revenue) / minted")
    ax.plot(idx, table["official"], marker="s", color=BLUE, lw=1.2, ls="--", label="revenue.near.org: revenue as % of emissions")
    ax.set_xticks(idx)
    ax.set_xticklabels([f"{p[2:4]}-{p[5:]}" for p in table.index], fontsize=8.5)
    _pct(ax)
    ax.set_ylim(0, max(0.35, float(table[["ours", "official"]].max().max()) * 1.15))
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_title("Share of issuance offset by revenue: independent estimate vs official dashboard")
    _save(fig, out, "coverage_official")


def usage(out, d, as_of):
    x = d.loc["2025-06-02":as_of]
    wk = pd.DataFrame(
        {
            "NEAR Intents volume (USD)": x["intents_volume_usd"].resample("W-SUN").sum(),
            "L1 transactions": x["txns"].resample("W-SUN").sum(),
            "Daily active accounts (weekly mean)": x["active_accounts"].resample("W-SUN").mean(),
            "Gas fees paid (NEAR)": x["txn_fee_near"].resample("W-SUN").sum(),
        }
    )
    wk = wk[wk.index <= as_of]
    base_week = wk.loc["2026-01-01":"2026-03-31"].mean()
    idx = wk / base_week * 100
    fig, ax = plt.subplots(figsize=(9, 4.0))
    colors = [GREEN, DARK, PURPLE, ORANGE]
    for (col, c) in zip(idx.columns, colors):
        ax.plot(idx.index, idx[col], lw=1.5, color=c, label=col)
    ax.set_yscale("log")
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

    lo, hi = ax.get_ylim()
    ticks = [t for t in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000) if lo <= t <= hi]
    ax.yaxis.set_major_locator(FixedLocator(ticks))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.axhline(100, color=GREY, lw=0.8)
    ax.set_ylabel("index, Q1 2026 average = 100 (log)")
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_title("Cross-chain volume vs L1 activity (weekly)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _save(fig, out, "usage")


def capture_rate(out, monthly):
    m = monthly.loc[(monthly.index >= "2025-06") & (monthly["intents_volume_usd"] > 0) & monthly["complete"].astype(bool)]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    idx = np.arange(len(m))
    ax.plot(idx, m["gross_fee_bps"], marker="o", color=GREY, label="Gross fees / volume (all integrators)")
    ax.plot(idx, m["net_capture_bps"], marker="o", color=GREEN, lw=1.8, label="NEAR's captured revenue / volume")
    ax.set_xticks(idx)
    ax.set_xticklabels([f"{p[2:4]}-{p[5:]}" + ("*" if not c else "") for p, c in zip(m.index, m["complete"])], fontsize=8)
    ax.set_ylabel("basis points of volume")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_title("NEAR Intents fee rate and NEAR's capture rate, by month")
    _save(fig, out, "capture_rate")


def leadlag_chart(out, ll):
    rows = ll["tests"]
    labels = [f"{r['predictor'].replace('_usd', '')} -> {r['target'].replace('_usd', '')}" for r in rows]
    raw = np.array([r["p_value"] for r in rows])
    adj = np.array([r["p_holm"] for r in rows])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = np.arange(len(rows))
    ax.barh(y - 0.18, raw, height=0.36, color=GREY, label="raw p (circular-shift test)")
    ax.barh(y + 0.18, adj, height=0.36, color=[GREEN if r["significant"] else BLUE for r in rows], label="Holm-adjusted p")
    ax.axvline(0.05, color=RED, ls="--", lw=1, label="5% threshold")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel(f"p-value: does adding {ll['lags']} weekly lags of the predictor improve an AR({ll['lags']}) model of the target?")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=8.5)
    ax.set_title("Lead-lag tests on weekly log changes", pad=26)
    _save(fig, out, "leadlag")


def xcorr_chart(out, ll):
    names = {"intents_to_price": "Intents volume leads price?", "intents_to_gas": "Intents volume leads gas use?", "price_to_gas": "Price leads gas use?"}
    fig, axes = plt.subplots(1, 3, figsize=(9, 3.0), sharey=True)
    for ax, (k, title) in zip(axes, names.items()):
        xc = ll["xcorr"][k]
        lags, c = np.array(xc["lags"]), np.array(xc["corr"])
        ax.bar(lags, c, color=[GREEN if v >= 0 else ORANGE for v in c], width=0.8)
        ax.axhspan(-xc["band95"], xc["band95"], color=GREY, alpha=0.2, lw=0)
        ax.axvline(0, color=DARK, lw=0.6)
        ax.set_title(title, fontsize=9.5)
        ax.set_xlabel("lag k (weeks); k>0: first series leads", fontsize=8)
    axes[0].set_ylabel("correlation")
    fig.suptitle("Cross-correlations of weekly log changes (grey = 95% band from circular shifts)", fontsize=10, fontweight="bold", y=1.03)
    _save(fig, out, "xcorr")


def reflexivity(out, monthly, start_month):
    m = monthly.loc[(monthly.index >= "2026-01") & monthly["complete"].astype(bool)]
    q1 = m.loc[m.index <= "2026-03"]
    base = q1[["intents_revenue_usd", "intents_revenue_near", "avg_price_usd"]].mean()
    fig, ax = plt.subplots(figsize=(9, 3.6))
    idx = np.arange(len(m))
    ax.plot(idx, m["intents_revenue_usd"] / base["intents_revenue_usd"], marker="o", color=GREEN, lw=1.8, label="Intents revenue in USD")
    ax.plot(idx, m["intents_revenue_near"] / base["intents_revenue_near"], marker="o", color=DARK, lw=1.4, label="Intents revenue in NEAR")
    ax.plot(idx, m["avg_price_usd"] / base["avg_price_usd"], marker=".", color=ORANGE, lw=1.2, ls="--", label="NEAR price (monthly mean)")
    ax.axhline(1, color=GREY, lw=0.8)
    ax.set_xticks(idx)
    ax.set_xticklabels([f"{p[2:4]}-{p[5:]}" for p in m.index], fontsize=8.5)
    ax.set_ylabel("multiple of Q1 2026 monthly average")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.set_title("Revenue in USD vs revenue in NEAR: price rises raise the bar")
    _save(fig, out, "reflexivity")


def wallets(out, w, cap_daily, start):
    fig, ax = plt.subplots(figsize=(9, 3.8))
    colors = {"buybacks.multisignature.near": GREEN, "fefundsadmin.sputnik-dao.near": BLUE, "1csfundsadmin.sputnik-dao.near": PURPLE}
    for acc, g in w.groupby("account_id"):
        ax.plot(g["time"], g["balance_near"], marker=".", ms=4, lw=1.4, color=colors.get(acc, GREY), label=f"{acc} (RPC view_account)")
    cum = cap_daily.loc[pd.Timestamp(start):, "intents_buyback_near"].cumsum()
    ax.plot(cum.index, cum.values, color=ORANGE, lw=1.2, ls="--", label="Cumulative buybacks per DefiLlama (USD / price)")
    ax.axvline(pd.Timestamp(start), color=RED, lw=0.8, ls=":", label=f"Buyback program start ({pd.Timestamp(start):%Y-%m-%d})")
    _human(ax)
    ax.set_ylabel("NEAR")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("Where captured revenue sits: native NEAR balances of revenue wallets")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _save(fig, out, "wallets")


def breakeven(out, be):
    rows = be["scenarios"]
    fig, ax = plt.subplots(figsize=(9, 3.4))
    labels = [("observed: " if r["observed"] else "") + f"{100 * r['growth_per_year']:.0f}%/yr" for r in rows]
    vals = [r["years_to_breakeven"] if r["years_to_breakeven"] is not None else np.nan for r in rows]
    y = np.arange(len(rows))
    ax.barh(y, vals, color=[ORANGE if r["observed"] else GREEN for r in rows])
    for yi, v in zip(y, vals):
        if np.isfinite(v):
            ax.text(v + 0.05, yi, f"{v:.1f} yrs", va="center", fontsize=9)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("years until usage-based capture >= issuance (constant NEAR price, constant capture rate)")
    ax.set_title(f"Break-even scenarios: revenue must grow {be['multiple']:.1f}x")
    _save(fig, out, "breakeven")


def data_checks(out, fees_m, price):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.4))
    r = fees_m["llama_chain_fees_usd"] / fees_m["txn_fee_usd"] - 1
    a1.bar(r.index, r.values, width=20, color=BLUE)
    _pct(a1)
    a1.set_title("Monthly gas fees: DefiLlama vs NearBlocks", fontsize=9.5)
    a1.set_ylabel("DefiLlama / NearBlocks - 1")
    a1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    rel = price["price_usd"] / price["cg_price_usd"] - 1
    a2.plot(rel.index, rel.values, color=PURPLE, lw=1)
    _pct(a2, digits=1)
    a2.set_title("Daily price: NearBlocks vs CoinGecko", fontsize=9.5)
    a2.set_ylabel("NearBlocks / CoinGecko - 1")
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _save(fig, out, "data_checks")
