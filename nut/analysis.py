"""All numbers used in THESIS.md and the dashboard are computed here from the parsed raw data."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import leadlag
from .util import clean_number

DAY_S = 86400.0
YEAR_S = 365.0 * DAY_S


# -- helpers -------------------------------------------------------------------------------------

def spread_over_days(starts: pd.Series, ends: pd.Series, values: pd.Series) -> pd.Series:
    """Allocate each interval's value to UTC days in proportion to time overlap."""
    acc: dict[pd.Timestamp, float] = {}
    for s, e, v in zip(starts, ends, values):
        total = (e - s).total_seconds()
        if total <= 0:
            continue
        day = s.normalize()
        while day < e:
            nxt = day + pd.Timedelta(days=1)
            ov = (min(e, nxt) - max(s, day)).total_seconds()
            if ov > 0:
                acc[day] = acc.get(day, 0.0) + v * ov / total
            day = nxt
    return pd.Series(acc).sort_index()


def full_days(starts: pd.Series, ends: pd.Series) -> pd.DatetimeIndex:
    first = starts.min().normalize() + pd.Timedelta(days=1)
    last = ends.max().normalize() - pd.Timedelta(days=1)
    return pd.date_range(first, last, freq="D")


def as_of_date(d: pd.DataFrame, fetched_at: str) -> pd.Timestamp:
    """Last UTC day that is complete in every core source."""
    fetch_day = pd.Timestamp(fetched_at).tz_localize(None).normalize() if pd.Timestamp(fetched_at).tzinfo is None else pd.Timestamp(fetched_at).tz_convert(None).normalize()
    core = ["total_supply_near", "price_usd", "txn_fee_near", "intents_volume_usd", "intents_revenue_usd"]
    last = min(d[c].dropna().index.max() for c in core)
    return min(last, fetch_day - pd.Timedelta(days=1))


# -- sections ------------------------------------------------------------------------------------

def issuance_section(d: pd.DataFrame, ep: pd.DataFrame, samples: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    out: dict = {}
    # RPC epochs (direct measurement)
    span = ep["duration_s"].sum()
    out["rpc_epochs"] = int(len(ep))
    out["rpc_first_epoch_start"] = ep["start"].min().strftime("%Y-%m-%d %H:%M")
    out["rpc_last_epoch_end"] = ep["next_start"].max().strftime("%Y-%m-%d %H:%M")
    out["rpc_minted_near"] = float(ep["minted_near"].sum())
    out["rpc_burnt_near"] = float(ep["burnt_near"].sum())
    out["rpc_burn_over_mint"] = out["rpc_burnt_near"] / out["rpc_minted_near"]
    out["rpc_annualized_issuance"] = float(ep["minted_near"].sum() / ep["supply_end_near"].mean() * YEAR_S / span)
    out["rpc_minted_per_day_near"] = float(ep["minted_near"].sum() / span * DAY_S)
    out["rpc_burnt_per_day_near"] = float(ep["burnt_near"].sum() / span * DAY_S)
    out["rpc_mean_epoch_hours"] = float(ep["duration_s"].mean() / 3600)

    # burn calibration: RPC-measured burn vs indexer-reported transaction fees on fully covered days
    burn_daily = spread_over_days(ep["start"], ep["next_start"], ep["burnt_near"])
    mint_daily = spread_over_days(ep["start"], ep["next_start"], ep["minted_near"])
    days = full_days(ep["start"], ep["next_start"])
    days = days[days.isin(d["txn_fee_near"].dropna().index)]
    if len(days) == 0:
        raise ValueError("RPC epochs do not cover any full day present in the NearBlocks data; increase rpc.epochs_back")
    fees = d.loc[days, "txn_fee_near"]
    beta = float(burn_daily.reindex(days).sum() / fees.sum())
    out["burn_to_fee_ratio"] = beta
    out["burn_calibration_days"] = int(len(days))

    # indexer-based minted NEAR per day: net supply change + burn
    supply = d["total_supply_near"]
    minted = supply.diff() + beta * d["txn_fee_near"]
    # validation against direct RPC minting on the same days
    nb_mint = minted.reindex(days)
    rpc_mint = mint_daily.reindex(days)
    out["mint_check_indexer_over_rpc"] = float(nb_mint.sum() / rpc_mint.sum())

    # supply cross-check: RPC header vs indexer daily value (indexer value is compared with the sample's day)
    s = samples.copy()
    s["day"] = s["time"].dt.normalize()
    s = s[s["day"].isin(supply.index)]
    rel = (s["total_supply_near"].values - supply.reindex(s["day"]).values) / s["total_supply_near"].values
    rel_next = (s["total_supply_near"].values - supply.reindex(s["day"] + pd.Timedelta(days=1)).values) / s["total_supply_near"].values
    out["supply_check_samples"] = int(np.isfinite(rel).sum())
    out["supply_check_median_abs_rel_diff"] = float(np.nanmedian(np.abs(rel)))
    out["supply_check_max_abs_rel_diff"] = float(np.nanmax(np.abs(rel)))
    out["supply_check_median_abs_rel_diff_next_day"] = float(np.nanmedian(np.abs(rel_next)))

    # gross issuance rate by month (indexer) and regime change
    gross_rate_7d = (minted.rolling(7).sum() / supply) * 365 / 7
    out["_gross_rate_7d"] = gross_rate_7d
    out["_minted_daily"] = minted
    # regime change: centered 7-day window, first day after which the rate stays below 3.75% for 60 days
    centered = (minted.rolling(7, center=True).sum() / supply) * 365 / 7
    hist = centered.loc[: as_of].dropna()
    vals = (hist < 0.0375).values
    idx = hist.index
    change = None
    for i in range(1, len(vals) - 60):
        if vals[i] and not vals[i - 1] and vals[i : i + 60].all():
            change = idx[i]
    out["halving_detected_on"] = change.strftime("%Y-%m-%d") if change is not None else None
    if change is not None:
        pre = slice(change - pd.Timedelta(days=365), change - pd.Timedelta(days=8))
        post = slice(change + pd.Timedelta(days=7), as_of)
        out["gross_issuance_rate_before"] = float(minted.loc[pre].sum() / supply.loc[pre].mean() * 365 / len(minted.loc[pre]))
        out["gross_issuance_rate_after"] = float(minted.loc[post].sum() / supply.loc[post].mean() * 365 / len(minted.loc[post]))
    out["total_supply_near_as_of"] = float(supply.loc[as_of])
    return out


def capture_section(d: pd.DataFrame, minted: pd.Series, beta: float, as_of: pd.Timestamp, cfg: dict) -> dict:
    out: dict = {}
    x = pd.DataFrame(index=d.index)
    x["minted_near"] = minted
    x["burn_near"] = beta * d["txn_fee_near"]
    x["price_usd"] = d["price_usd"]
    x["intents_volume_usd"] = d["intents_volume_usd"].fillna(0.0)
    x["intents_fees_usd"] = d["intents_fees_usd"].fillna(0.0)
    x["intents_revenue_usd"] = d["intents_revenue_usd"].fillna(0.0)
    x["intents_buyback_usd"] = d["intents_buyback_usd"].fillna(0.0)
    x["intents_revenue_near"] = x["intents_revenue_usd"] / x["price_usd"]
    x["intents_buyback_near"] = x["intents_buyback_usd"] / x["price_usd"]
    x["minted_usd"] = x["minted_near"] * x["price_usd"]
    x["burn_usd"] = x["burn_near"] * x["price_usd"]
    x["gas_fees_usd"] = d["txn_fee_usd"]
    x = x.loc[:as_of]
    out["_daily"] = x

    def window(days: int | None = None, start: str | None = None) -> dict:
        w = x.loc[pd.Timestamp(start) : as_of] if start else x.loc[as_of - pd.Timedelta(days=days - 1) : as_of]
        res = {
            "start": w.index.min().strftime("%Y-%m-%d"),
            "end": w.index.max().strftime("%Y-%m-%d"),
            "days": int(len(w)),
            "minted_near": float(w["minted_near"].sum()),
            "burn_near": float(w["burn_near"].sum()),
            "intents_revenue_near": float(w["intents_revenue_near"].sum()),
            "intents_revenue_usd": float(w["intents_revenue_usd"].sum()),
            "intents_buyback_near": float(w["intents_buyback_near"].sum()),
            "intents_volume_usd": float(w["intents_volume_usd"].sum()),
            "intents_fees_usd": float(w["intents_fees_usd"].sum()),
            "minted_usd": float(w["minted_usd"].sum()),
            "burn_usd": float(w["burn_usd"].sum()),
            "gas_fees_usd": float(w["gas_fees_usd"].sum()),
            "avg_price_usd": float(w["price_usd"].mean()),
        }
        res["coverage_burn"] = res["burn_near"] / res["minted_near"]
        res["coverage_intents"] = res["intents_revenue_near"] / res["minted_near"]
        res["coverage_total"] = res["coverage_burn"] + res["coverage_intents"]
        res["coverage_total_usd"] = (res["burn_usd"] + res["intents_revenue_usd"]) / res["minted_usd"]
        res["intents_share_of_capture"] = res["intents_revenue_near"] / (res["intents_revenue_near"] + res["burn_near"])
        res["intents_revenue_over_gas_fees"] = res["intents_revenue_usd"] / res["gas_fees_usd"]
        res["net_capture_bps"] = 1e4 * res["intents_revenue_usd"] / res["intents_volume_usd"] if res["intents_volume_usd"] else None
        res["gross_fee_bps"] = 1e4 * res["intents_fees_usd"] / res["intents_volume_usd"] if res["intents_volume_usd"] else None
        res["effective_emissions_near"] = res["minted_near"] - res["burn_near"] - res["intents_buyback_near"]
        res["breakeven_multiple"] = res["minted_usd"] / (res["burn_usd"] + res["intents_revenue_usd"])
        return res

    for wd in cfg["analysis"]["windows"]:
        out[f"d{wd}"] = window(days=int(wd))
    out["since_buyback"] = window(start=cfg["analysis"]["buyback_program_start"])
    out["ytd"] = window(start=f"{as_of.year}-01-01")

    # monthly table (complete months only, plus the partial current month flagged)
    m = x.loc["2025-01-01":].resample("ME").sum(numeric_only=True)
    m["days"] = x.loc["2025-01-01":].resample("ME").size()
    m["coverage_burn"] = m["burn_near"] / m["minted_near"]
    m["coverage_intents"] = m["intents_revenue_near"] / m["minted_near"]
    m["coverage_total"] = m["coverage_burn"] + m["coverage_intents"]
    m["net_capture_bps"] = 1e4 * m["intents_revenue_usd"] / m["intents_volume_usd"].replace(0, np.nan)
    m["gross_fee_bps"] = 1e4 * m["intents_fees_usd"] / m["intents_volume_usd"].replace(0, np.nan)
    m["avg_price_usd"] = x.loc["2025-01-01":, "price_usd"].resample("ME").mean()
    m.index = m.index.to_period("M").astype(str)
    month_end = as_of + pd.offsets.MonthEnd(0)
    m["complete"] = [pd.Period(i).end_time.normalize() <= as_of for i in m.index]
    out["_monthly"] = m
    complete = m[m["complete"]]
    last = complete.iloc[-1]
    out["last_full_month"] = complete.index[-1]
    out["last_full_month_coverage_total"] = float(last["coverage_total"])
    out["last_full_month_coverage_burn"] = float(last["coverage_burn"])
    out["last_full_month_coverage_intents"] = float(last["coverage_intents"])
    since = complete.loc[complete.index >= "2026-01"]
    out["coverage_2026_min"] = float(since["coverage_total"].min())
    out["coverage_2026_max"] = float(since["coverage_total"].max())
    out["coverage_2026_min_month"] = since["coverage_total"].idxmin()
    out["coverage_2026_max_month"] = since["coverage_total"].idxmax()
    material = complete.loc[complete["intents_revenue_usd"] >= 50_000]
    out["net_bps_first_month"] = material.index[0]
    out["net_bps_first_value"] = float(material.iloc[0]["net_capture_bps"])
    out["net_bps_last_value"] = float(last["net_capture_bps"])
    # USD revenue growth vs NEAR revenue growth: Q1 2026 monthly average vs the last 3 complete months
    q1 = complete.loc[(complete.index >= "2026-01") & (complete.index <= "2026-03")]
    last3 = complete.iloc[-3:]
    if len(q1) == 3:
        out["growth_from_month"] = "Q1 2026"
        out["growth_to_months"] = f"{last3.index[0]}..{last3.index[-1]}"
        out["revenue_usd_growth_multiple"] = float(last3["intents_revenue_usd"].mean() / q1["intents_revenue_usd"].mean())
        out["revenue_near_growth_multiple"] = float(last3["intents_revenue_near"].mean() / q1["intents_revenue_near"].mean())
        out["price_growth_multiple"] = float(last3["avg_price_usd"].mean() / q1["avg_price_usd"].mean())
        out["coverage_q1_2026"] = float((q1["burn_near"].sum() + q1["intents_revenue_near"].sum()) / q1["minted_near"].sum())
        out["coverage_last3"] = float((last3["burn_near"].sum() + last3["intents_revenue_near"].sum()) / last3["minted_near"].sum())
    del month_end
    return out


def official_section(official: dict, monthly: pd.DataFrame) -> dict:
    out: dict = {"available": bool(official.get("emissionsMonthly"))}
    if not out["available"]:
        return out
    om = pd.Series({str(r["date"])[:7]: float(r["value"]) / 100 for r in official["emissionsMonthly"]})
    both = pd.DataFrame({"ours": monthly["coverage_total"], "official": om, "complete": monthly["complete"]}).dropna()
    both = both[both["complete"].astype(bool)]
    both = both.loc[both.index >= "2026-01"]
    diff = (both["ours"] - both["official"]) * 100
    out["_table"] = both
    out["months_compared"] = int(len(both))
    out["mean_abs_diff_pp"] = float(diff.abs().mean())
    out["max_abs_diff_pp"] = float(diff.abs().max())
    out["max_abs_diff_month"] = diff.abs().idxmax()
    out["months_within_5pp"] = int((diff.abs() <= 5).sum())
    out["official_mean"] = float(both["official"].mean())
    out["ours_mean"] = float(both["ours"].mean())
    if official.get("absoluteRevEmissions"):
        last = official["absoluteRevEmissions"][-1]
        out["official_ytd_date"] = last["date"]
        out["official_ytd_emissions_near"] = float(last["emissionsNear"])
        out["official_ytd_revenue_near"] = float(last["revenueNear"])
        out["official_ytd_offset"] = float(last["revenueNear"]) / float(last["emissionsNear"])
        ours = monthly.loc[(monthly.index >= str(last["date"])[:4] + "-01") & (monthly.index <= str(last["date"])[:7])]
        out["ours_ytd_offset_same_months"] = float((ours["burn_near"].sum() + ours["intents_revenue_near"].sum()) / ours["minted_near"].sum())
    out["updated"] = official.get("updated")
    return out


def usage_section(d: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    out: dict = {}
    x = d.loc[:as_of]
    mon = x[["txns", "active_accounts", "new_accounts", "intents_volume_usd", "txn_fee_near"]].resample("ME").agg(
        {"txns": "sum", "active_accounts": "mean", "new_accounts": "sum", "intents_volume_usd": "sum", "txn_fee_near": "sum"}
    )
    mon = mon[mon.index <= as_of + pd.offsets.MonthEnd(0)]
    complete = mon[mon.index <= as_of]
    if as_of != as_of + pd.offsets.MonthEnd(0):
        complete = mon[mon.index < as_of.normalize().replace(day=1)]
    peak_m = complete["txns"].idxmax()
    out["txns_peak_month"] = peak_m.strftime("%Y-%m")
    out["txns_peak_month_value"] = float(complete.loc[peak_m, "txns"])
    lastm = complete.index[-1]
    out["last_full_month"] = lastm.strftime("%Y-%m")
    out["txns_last_month_value"] = float(complete.loc[lastm, "txns"])
    out["txns_change_from_peak"] = out["txns_last_month_value"] / out["txns_peak_month_value"] - 1
    # Q1 2026 vs last 90 days
    q1 = x.loc["2026-01-01":"2026-03-31"]
    l90 = x.loc[as_of - pd.Timedelta(days=89) : as_of]
    for col in ["txns", "active_accounts", "intents_volume_usd", "txn_fee_near"]:
        out[f"{col}_q1_2026_daily"] = float(q1[col].mean())
        out[f"{col}_last90_daily"] = float(l90[col].mean())
        out[f"{col}_change_q1_to_last90"] = float(l90[col].mean() / q1[col].mean() - 1)
    # step change in April 2026 (both indexers)
    mar, apr = x.loc["2026-03-01":"2026-03-31"], x.loc["2026-04-01":"2026-04-30"]
    out["txns_mar_to_apr_2026"] = float(apr["txns"].sum() / mar["txns"].sum() - 1)
    out["fees_mar_to_apr_2026_nearblocks"] = float(apr["txn_fee_usd"].sum() / mar["txn_fee_usd"].sum() - 1)
    out["fees_mar_to_apr_2026_defillama"] = float(apr["llama_chain_fees_usd"].sum() / mar["llama_chain_fees_usd"].sum() - 1)
    out["_monthly"] = mon
    # Intents volume growth: trailing 90 days vs the same 90 days one year earlier
    prev = x.loc[as_of - pd.Timedelta(days=365 + 89) : as_of - pd.Timedelta(days=365), "intents_volume_usd"]
    out["intents_volume_last90"] = float(l90["intents_volume_usd"].sum())
    out["intents_volume_prev_year_90"] = float(prev.sum())
    out["intents_volume_yoy_multiple"] = float(l90["intents_volume_usd"].sum() / prev.sum())
    out["intents_volume_all_time"] = float(x["intents_volume_usd"].sum())
    return out


def data_checks_section(d: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    out: dict = {}
    x = d.loc[:as_of]
    m = x[["txn_fee_usd", "llama_chain_fees_usd"]].loc["2021-01-01":].resample("ME").sum()
    m = m[(m > 0).all(axis=1)]
    m = m[m.index <= as_of]
    ratio = m["llama_chain_fees_usd"] / m["txn_fee_usd"]
    out["_fees_monthly"] = m
    out["fees_months_compared"] = int(len(ratio))
    out["fees_ratio_median"] = float(ratio.median())
    last24 = ratio.iloc[-24:]
    out["fees_ratio_last24_min"] = float(last24.min())
    out["fees_ratio_last24_max"] = float(last24.max())
    p = x[["price_usd", "cg_price_usd"]].dropna()
    rel = (p["price_usd"] / p["cg_price_usd"] - 1).abs()
    out["price_days_compared"] = int(len(p))
    out["price_median_abs_rel_diff"] = float(rel.median())
    out["price_p95_abs_rel_diff"] = float(rel.quantile(0.95))
    out["_price"] = p
    return out


def wallets_section(w: pd.DataFrame, cap_daily: pd.DataFrame, cfg: dict) -> dict:
    out: dict = {}
    start = pd.Timestamp(cfg["analysis"]["buyback_program_start"])
    bb = w[w["account_id"] == "buybacks.multisignature.near"].sort_values("time")
    out["_wallets"] = w
    if bb.empty:
        out["available"] = False
        return out
    out["available"] = True
    last = bb.iloc[-1]
    out["buyback_wallet_latest_near"] = float(last["balance_near"])
    out["buyback_wallet_latest_time"] = last["time"].strftime("%Y-%m-%d")
    before = bb[bb["time"] <= start]
    out["buyback_wallet_at_start_near"] = float(before.iloc[-1]["balance_near"]) if len(before) else 0.0
    out["buyback_wallet_increase_near"] = out["buyback_wallet_latest_near"] - out["buyback_wallet_at_start_near"]
    # did the balance ever fall materially? (would indicate the NEAR is moved or spent)
    drops = bb["balance_near"].diff()
    out["buyback_wallet_largest_drop_near"] = float(-drops.min()) if drops.min() < 0 else 0.0
    cum = cap_daily.loc[start : last["time"].normalize(), "intents_buyback_near"].sum()
    out["defillama_buyback_near_same_period"] = float(cum)
    out["wallet_vs_defillama_ratio"] = out["buyback_wallet_increase_near"] / cum if cum else None
    summary = []
    for acc in w["account_id"].unique():
        a = w[w["account_id"] == acc].sort_values("time")
        out[f"latest_{acc}"] = float(a.iloc[-1]["balance_near"])
        over = a[a["balance_near"] >= 10_000]
        summary.append(
            {
                "account_id": acc,
                "latest_near": float(a.iloc[-1]["balance_near"]),
                "latest_time": a.iloc[-1]["time"].strftime("%Y-%m-%d"),
                "first_sample_over_10k": over.iloc[0]["time"].strftime("%Y-%m-%d") if len(over) else None,
            }
        )
    out["wallet_summary"] = summary
    return out


def breakeven_section(cap: dict, usage: dict, cfg: dict) -> dict:
    w = cap["d90"]
    out: dict = {}
    m = w["breakeven_multiple"]
    out["window"] = f'{w["start"]}..{w["end"]}'
    out["multiple"] = m
    out["coverage_total_usd"] = w["coverage_total_usd"]
    emissions_usd_day = w["minted_usd"] / w["days"]
    burn_usd_day = w["burn_usd"] / w["days"]
    bps = w["net_capture_bps"]
    out["net_capture_bps"] = bps
    out["required_daily_intents_volume_usd"] = (emissions_usd_day - burn_usd_day) / (bps / 1e4)
    out["current_daily_intents_volume_usd"] = w["intents_volume_usd"] / w["days"]
    out["required_volume_multiple"] = out["required_daily_intents_volume_usd"] / out["current_daily_intents_volume_usd"]
    out["required_annual_intents_volume_usd"] = out["required_daily_intents_volume_usd"] * 365
    g_obs = usage["intents_volume_yoy_multiple"] - 1
    rates = list(cfg["analysis"]["scenario_growth_rates"]) + [g_obs]
    rows = []
    for g in rates:
        years = math.log(m) / math.log(1 + g) if (m > 1 and g > 0) else (0.0 if m <= 1 else None)
        rows.append({"growth_per_year": g, "years_to_breakeven": years, "observed": g == g_obs})
    out["scenarios"] = rows
    out["observed_growth_per_year"] = g_obs
    out["years_at_observed_growth"] = rows[-1]["years_to_breakeven"]
    return out


def leadlag_section(d: pd.DataFrame, as_of: pd.Timestamp, cfg: dict) -> dict:
    a = cfg["analysis"]
    x = d.loc[:as_of]
    wk = pd.DataFrame(
        {
            "intents_volume_usd": x["intents_volume_usd"].resample("W-SUN").sum(),
            "price_usd": x["price_usd"].resample("W-SUN").last(),
            "gas_near": x["txn_fee_near"].resample("W-SUN").sum(),
            "txns": x["txns"].resample("W-SUN").sum(),
            "active_accounts": x["active_accounts"].resample("W-SUN").mean(),
        }
    )
    wk = wk[wk.index <= as_of]  # last complete week ends on or before as_of
    start = wk.index[wk["intents_volume_usd"] >= a["leadlag_min_weekly_intents_usd"]].min()
    wk = wk.loc[start:]
    g = np.log(wk).diff().dropna()
    p, ms = int(a["leadlag_lags"]), int(a["leadlag_min_shift_weeks"])
    tests = []
    usage_targets = ["gas_near", "txns", "active_accounts"]
    for target in usage_targets:
        for pred in ["intents_volume_usd", "price_usd"]:
            tests.append(("H2", pred, target))
    for pred in ["intents_volume_usd", "gas_near", "txns", "active_accounts"]:
        tests.append(("H3", pred, "price_usd"))
    rows = []
    for hyp, pred, target in tests:
        r = leadlag.shift_pvalue(g[target].values, g[pred].values, p, ms)
        rows.append({"hypothesis": hyp, "predictor": pred, "target": target, **r})
    adj = leadlag.holm([r["p_value"] for r in rows])
    for r, q in zip(rows, adj):
        r["p_holm"] = q
        r["significant"] = q < a["leadlag_alpha"]
    out = {
        "weeks": int(len(g)),
        "start_week": g.index.min().strftime("%Y-%m-%d"),
        "end_week": g.index.max().strftime("%Y-%m-%d"),
        "lags": p,
        "tests": rows,
        "n_tests": len(rows),
        "n_significant": int(sum(r["significant"] for r in rows)),
        "n_raw_below_alpha": int(sum(r["p_value"] < a["leadlag_alpha"] for r in rows)),
    }
    # compare predictors for each usage target (H2): which one has the larger R^2 gain?
    comp = []
    for target in usage_targets:
        iv = next(r for r in rows if r["predictor"] == "intents_volume_usd" and r["target"] == target)
        pr = next(r for r in rows if r["predictor"] == "price_usd" and r["target"] == target)
        comp.append({"target": target, "intents_r2_gain": iv["r2_gain"], "price_r2_gain": pr["r2_gain"],
                     "intents_p": iv["p_value"], "price_p": pr["p_value"],
                     "better": "intents_volume_usd" if iv["r2_gain"] > pr["r2_gain"] else "price_usd"})
    out["h2_comparison"] = comp
    out["h2_intents_better_count"] = int(sum(c["better"] == "intents_volume_usd" for c in comp))
    xc = {}
    for name, (yv, xv) in {
        "intents_to_price": ("price_usd", "intents_volume_usd"),
        "intents_to_gas": ("gas_near", "intents_volume_usd"),
        "price_to_gas": ("gas_near", "price_usd"),
    }.items():
        xc[name] = leadlag.xcorr(g[yv].values, g[xv].values, int(a["xcorr_max_lag"]), ms)
    out["xcorr"] = xc
    contemporaneous = float(np.corrcoef(g["intents_volume_usd"], g["price_usd"])[0, 1])
    out["corr_same_week_intents_price"] = contemporaneous
    out["_weekly"] = wk
    return out


def strip_private(obj):
    """Drop keys starting with '_' (tables) and clean floats for JSON."""
    if isinstance(obj, dict):
        return {k: strip_private(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [strip_private(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return clean_number(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj
