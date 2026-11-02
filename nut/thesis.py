"""Render THESIS.md from thesis/THESIS.template.md. Placeholders look like {{name}}; every one must resolve."""
from __future__ import annotations

import re

from .config import Paths
from .narrative import chart_specs
from .util import fmt_near, fmt_pct, fmt_usd

PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_\.]+)\}\}")


def values(m: dict) -> dict:
    iss, cap, use, ll, be, chk, wal, off, proto = (
        m[k] for k in ("issuance", "capture", "usage", "leadlag", "breakeven", "checks", "wallets", "official", "protocol")
    )
    d30, d90, sb, ytd = cap["d30"], cap["d90"], cap["since_buyback"], cap["ytd"]
    v = {
        "as_of": m["as_of"],
        "fetched_at": m["fetched_at"],
        "protocol_version": str(proto["protocol_version"]),
        "max_inflation": fmt_pct(proto["max_inflation_rate_float"], 1),
        "rpc_epochs": str(iss["rpc_epochs"]),
        "rpc_from": iss["rpc_first_epoch_start"][:10],
        "rpc_to": iss["rpc_last_epoch_end"][:10],
        "rpc_issuance": fmt_pct(iss["rpc_annualized_issuance"], 2),
        "rpc_minted": fmt_near(iss["rpc_minted_near"]),
        "rpc_burnt": fmt_near(iss["rpc_burnt_near"]),
        "rpc_minted_day": fmt_near(iss["rpc_minted_per_day_near"]),
        "rpc_burnt_day": fmt_near(iss["rpc_burnt_per_day_near"]),
        "rpc_burn_over_mint": fmt_pct(iss["rpc_burn_over_mint"], 2),
        "burn_to_fee": f"{iss['burn_to_fee_ratio']:.2f}",
        "burn_days": str(iss["burn_calibration_days"]),
        "mint_check": fmt_pct(iss["mint_check_indexer_over_rpc"] - 1, 2),
        "supply_samples": str(iss["supply_check_samples"]),
        "supply_max_diff": fmt_pct(iss["supply_check_max_abs_rel_diff"], 3),
        "supply_median_diff": fmt_pct(iss["supply_check_median_abs_rel_diff"], 4),
        "halving_date": str(iss["halving_detected_on"]),
        "rate_before": fmt_pct(iss["gross_issuance_rate_before"], 2),
        "rate_after": fmt_pct(iss["gross_issuance_rate_after"], 2),
        "supply_now": fmt_near(iss["total_supply_near_as_of"]),
        "last_month": cap["last_full_month"],
        "lm_cov": fmt_pct(cap["last_full_month_coverage_total"]),
        "lm_cov_burn": fmt_pct(cap["last_full_month_coverage_burn"], 1),
        "lm_cov_intents": fmt_pct(cap["last_full_month_coverage_intents"]),
        "cov26_min": fmt_pct(cap["coverage_2026_min"]),
        "cov26_max": fmt_pct(cap["coverage_2026_max"]),
        "cov26_min_m": cap["coverage_2026_min_month"],
        "cov26_max_m": cap["coverage_2026_max_month"],
        "bps_first": f"{cap['net_bps_first_value']:.1f}",
        "bps_first_m": cap["net_bps_first_month"],
        "bps_last": f"{cap['net_bps_last_value']:.1f}",
        "growth_from": cap.get("growth_from_month", "n/a"),
        "growth_to": cap.get("growth_to_months", "n/a"),
        "cov_q1": fmt_pct(cap.get("coverage_q1_2026", float("nan")), 1),
        "cov_last3": fmt_pct(cap.get("coverage_last3", float("nan")), 1),
        "rev_usd_mult": f"{cap.get('revenue_usd_growth_multiple', float('nan')):.1f}x",
        "rev_near_mult": f"{cap.get('revenue_near_growth_multiple', float('nan')):.1f}x",
        "price_mult": f"{cap.get('price_growth_multiple', float('nan')):.1f}x",
        "txns_peak_m": use["txns_peak_month"],
        "txns_peak": f"{use['txns_peak_month_value'] / 1e6:.0f}M",
        "txns_last": f"{use['txns_last_month_value'] / 1e6:.1f}M",
        "txns_last_m": use["last_full_month"],
        "txns_from_peak": f"{100 * use['txns_change_from_peak']:+.0f}%",
        "txns_q1_chg": f"{100 * use['txns_change_q1_to_last90']:+.0f}%",
        "aa_q1_chg": f"{100 * use['active_accounts_change_q1_to_last90']:+.0f}%",
        "iv_q1_chg": f"{100 * use['intents_volume_usd_change_q1_to_last90']:+.0f}%",
        "gas_q1_chg": f"{100 * use['txn_fee_near_change_q1_to_last90']:+.0f}%",
        "txns_mar_apr": f"{100 * use['txns_mar_to_apr_2026']:+.0f}%",
        "fees_mar_apr_nb": f"{100 * use['fees_mar_to_apr_2026_nearblocks']:+.0f}%",
        "fees_mar_apr_ll": f"{100 * use['fees_mar_to_apr_2026_defillama']:+.0f}%",
        "iv_all_time": fmt_usd(use["intents_volume_all_time"]),
        "iv_last90": fmt_usd(use["intents_volume_last90"]),
        "iv_prev90": fmt_usd(use["intents_volume_prev_year_90"]),
        "iv_yoy": f"{use['intents_volume_yoy_multiple']:.1f}x",
        "fees_lo": f"{100 * (chk['fees_ratio_last24_min'] - 1):+.1f}%",
        "fees_hi": f"{100 * (chk['fees_ratio_last24_max'] - 1):+.1f}%",
        "fees_months": str(chk["fees_months_compared"]),
        "price_p95": fmt_pct(chk["price_p95_abs_rel_diff"], 1),
        "price_days": str(chk["price_days_compared"]),
        "be_multiple": f"{be['multiple']:.1f}x",
        "be_cov": fmt_pct(be["coverage_total_usd"], 1),
        "be_bps": f"{be['net_capture_bps']:.1f}",
        "be_req_day": fmt_usd(be["required_daily_intents_volume_usd"]),
        "be_req_year": fmt_usd(be["required_annual_intents_volume_usd"]),
        "be_cur_day": fmt_usd(be["current_daily_intents_volume_usd"]),
        "be_vol_mult": f"{be['required_volume_multiple']:.1f}x",
        "be_obs_g": fmt_pct(be["observed_growth_per_year"], 0),
        "be_obs_years": f"{be['years_at_observed_growth']:.1f}" if be["years_at_observed_growth"] is not None else "n/a",
        "ll_weeks": str(ll["weeks"]),
        "ll_start": ll["start_week"],
        "ll_end": ll["end_week"],
        "ll_lags": str(ll["lags"]),
        "ll_n": str(ll["n_tests"]),
        "ll_sig": str(ll["n_significant"]),
        "ll_raw": str(ll["n_raw_below_alpha"]),
        "ll_corr_same": f"{ll['corr_same_week_intents_price']:.2f}",
        "h2_better": str(ll["h2_intents_better_count"]),
        "txns_peak_drop": f"{abs(100 * use['txns_change_from_peak']):.0f}%",
        "mint_check_abs": fmt_pct(abs(iss["mint_check_indexer_over_rpc"] - 1), 2),
    }
    h2 = [t for t in ll["tests"] if t["hypothesis"] == "H2"]
    h3 = [t for t in ll["tests"] if t["hypothesis"] == "H3"]
    h2_sig, h3_sig = sum(t["significant"] for t in h2), sum(t["significant"] for t in h3)
    v["h2_n"], v["h2_sig"] = str(len(h2)), str(h2_sig)
    v["h3_n"], v["h3_sig"] = str(len(h3)), str(h3_sig)
    v["h3_min_p"] = f"{min(t['p_value'] for t in h3):.2f}" if h3 else "n/a"
    v["h1_verdict"] = "Reached" if d90["coverage_total"] >= 1 else "Not reached"
    if h2_sig == 0 and ll["h2_intents_better_count"] <= 1:
        v["h2_verdict"] = "Not supported"
    elif h2_sig > 0 and ll["h2_intents_better_count"] >= 2:
        v["h2_verdict"] = "Supported"
    else:
        v["h2_verdict"] = "Mixed"
    v["h3_verdict"] = "Not supported" if h3_sig == 0 else "Partly supported"
    v["be_50_years"] = next(
        (f"{r['years_to_breakeven']:.1f}" for r in be["scenarios"] if abs(r["growth_per_year"] - 0.5) < 1e-9 and r["years_to_breakeven"] is not None),
        "n/a",
    )
    for w, tag in ((d30, "d30"), (d90, "d90"), (sb, "sb"), (ytd, "ytd")):
        v[f"{tag}_start"] = w["start"]
        v[f"{tag}_end"] = w["end"]
        v[f"{tag}_minted"] = fmt_near(w["minted_near"])
        v[f"{tag}_burn"] = fmt_near(w["burn_near"])
        v[f"{tag}_rev_near"] = fmt_near(w["intents_revenue_near"])
        v[f"{tag}_rev_usd"] = fmt_usd(w["intents_revenue_usd"])
        v[f"{tag}_buyback"] = fmt_near(w["intents_buyback_near"])
        v[f"{tag}_cov_burn"] = fmt_pct(w["coverage_burn"], 2)
        v[f"{tag}_cov_int"] = fmt_pct(w["coverage_intents"], 1)
        v[f"{tag}_cov"] = fmt_pct(w["coverage_total"], 1)
        v[f"{tag}_cov_usd"] = fmt_pct(w["coverage_total_usd"], 1)
        v[f"{tag}_eff"] = fmt_near(w["effective_emissions_near"])
        v[f"{tag}_share_int"] = fmt_pct(w["intents_share_of_capture"], 0)
        v[f"{tag}_rev_over_gas"] = f"{w['intents_revenue_over_gas_fees']:.0f}x"
        v[f"{tag}_gas_usd"] = fmt_usd(w["gas_fees_usd"])
        v[f"{tag}_vol"] = fmt_usd(w["intents_volume_usd"])
    if off.get("available"):
        v.update(
            {
                "off_n": str(off["months_compared"]),
                "off_mad": f"{off['mean_abs_diff_pp']:.1f}",
                "off_max": f"{off['max_abs_diff_pp']:.1f}",
                "off_max_m": off["max_abs_diff_month"],
                "off_within5": str(off["months_within_5pp"]),
                "off_mean": fmt_pct(off["official_mean"], 1),
                "ours_mean": fmt_pct(off["ours_mean"], 1),
                "off_ytd": fmt_pct(off.get("official_ytd_offset", float("nan")), 1),
                "off_ytd_date": str(off.get("official_ytd_date")),
                "ours_ytd_same": fmt_pct(off.get("ours_ytd_offset_same_months", float("nan")), 1),
            }
        )
    if wal.get("available"):
        v.update(
            {
                "bb_latest": fmt_near(wal["buyback_wallet_latest_near"]),
                "bb_date": wal["buyback_wallet_latest_time"],
                "bb_start": fmt_near(wal["buyback_wallet_at_start_near"]),
                "bb_inc": fmt_near(wal["buyback_wallet_increase_near"]),
                "bb_dl": fmt_near(wal["defillama_buyback_near_same_period"]),
                "bb_ratio": f"{wal['wallet_vs_defillama_ratio']:.2f}" if wal.get("wallet_vs_defillama_ratio") else "n/a",
                "bb_drop": fmt_near(wal["buyback_wallet_largest_drop_near"]),
            }
        )
        rows = {r["account_id"]: r for r in wal.get("wallet_summary", [])}
        bbr = rows.get("buybacks.multisignature.near", {})
        fe = rows.get("fefundsadmin.sputnik-dao.near", {})
        v["bb_first10k"] = str(bbr.get("first_sample_over_10k"))
        v["bb_ratio_pct"] = fmt_pct(wal["wallet_vs_defillama_ratio"], 0) if wal.get("wallet_vs_defillama_ratio") else "n/a"
        v["fe_latest"] = fmt_near(fe["latest_near"]) if fe else "n/a"
        v["fe_first10k"] = str(fe.get("first_sample_over_10k")) if fe else "n/a"
    rows = []
    for t in ll["tests"]:
        rows.append(
            f"| {t['hypothesis']} | `{t['predictor']}` -> `{t['target']}` | {t['f']:.2f} | {100 * t['r2_gain']:.1f}% | {t['p_value']:.3f} | {t['p_holm']:.3f} | {'yes' if t['significant'] else 'no'} |"
        )
    v["leadlag_table"] = "\n".join(rows)
    srows = []
    for r in be["scenarios"]:
        yrs = "already" if r["years_to_breakeven"] == 0 else (f"{r['years_to_breakeven']:.1f}" if r["years_to_breakeven"] is not None else "never")
        srows.append(f"| {fmt_pct(r['growth_per_year'], 0)}{' (observed YoY volume growth)' if r['observed'] else ''} | {yrs} |")
    v["scenario_table"] = "\n".join(srows)
    v["chart_list"] = "\n".join(f"{i}. **{s['title'].split('. ', 1)[-1]}** - {s['sentence']}" for i, s in enumerate(chart_specs(m), 1))
    return v


def render(template: str, v: dict) -> str:
    missing = sorted({k for k in PLACEHOLDER.findall(template) if k not in v})
    if missing:
        raise KeyError(f"THESIS template placeholders without a computed value: {missing}")
    return PLACEHOLDER.sub(lambda mt: v[mt.group(1)], template)


def write(paths: Paths, m: dict) -> None:
    tpl = paths.thesis_template.read_text(encoding="utf-8")
    paths.thesis.write_text(render(tpl, values(m)), encoding="utf-8")
