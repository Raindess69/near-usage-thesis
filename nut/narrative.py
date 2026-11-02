"""Chart titles, data sources and one plain sentence per chart. Every number is read from metrics."""
from __future__ import annotations

from .util import fmt_near, fmt_pct, fmt_usd

NB = "https://api.nearblocks.io/v1/charts"
LL_VOL = "https://api.llama.fi/summary/dexs/near-intents"
LL_FEES = "https://api.llama.fi/summary/fees/near-intents?dataType=dailyFees"
LL_REV = "https://api.llama.fi/summary/fees/near-intents?dataType=dailyRevenue"
LL_HREV = "https://api.llama.fi/summary/fees/near-intents?dataType=dailyHoldersRevenue"
LL_CHAIN = "https://api.llama.fi/summary/fees/near?dataType=dailyFees"
CG = "https://api.coingecko.com/api/v3/coins/near/market_chart?vs_currency=usd&days=365"
RPC = "archival JSON-RPC `block` (fields total_supply, chunks[].balance_burnt, next_epoch_id)"
OFF = "https://revenue.near.org/ (series embedded in the page: emissionsMonthly)"


def _signed(x: float) -> str:
    return f"{100 * x:+.0f}%"


def chart_specs(m: dict) -> list[dict]:
    iss, cap, use, ll, be, chk, wal, off = (m[k] for k in ("issuance", "capture", "usage", "leadlag", "breakeven", "checks", "wallets", "official"))
    lm = cap["last_full_month"]
    specs = [
        {
            "id": "issuance",
            "title": "1. Issuance: supply growth was cut in half",
            "sentence": (
                f"Gross issuance ran at {fmt_pct(iss['gross_issuance_rate_before'], 2)} a year before {iss['halving_detected_on']} "
                f"and {fmt_pct(iss['gross_issuance_rate_after'], 2)} after it; {iss['supply_check_samples']} archival block headers "
                f"match the indexer's daily supply within {fmt_pct(iss['supply_check_max_abs_rel_diff'], 3)}."
            ),
            "sources": [f"{NB} (total_supply, txn_fee)", f"{RPC}, one header every 2,000,000 heights"],
            "method": "minted(day) = total_supply(day) - total_supply(day-1) + beta * txn_fee(day); rate = 7-day minted / supply * 365/7. beta is the RPC-measured burn/fee ratio (chart 2).",
            "code": "nut/analysis.py::issuance_section",
            "csv": "data/processed/daily.csv",
        },
        {
            "id": "epochs",
            "title": "2. Onchain check: burn vs minting per epoch",
            "sentence": (
                f"Over the last {iss['rpc_epochs']} epochs ({iss['rpc_first_epoch_start'][:10]} to {iss['rpc_last_epoch_end'][:10]}) the protocol minted "
                f"{fmt_near(iss['rpc_minted_near'])} and burnt {fmt_near(iss['rpc_burnt_near'])}, so gas burn offset only "
                f"{fmt_pct(iss['rpc_burn_over_mint'], 2)} of issuance ({fmt_pct(iss['rpc_annualized_issuance'], 2)} a year)."
            ),
            "sources": [RPC],
            "method": "For each epoch: minted = supply(first block of next epoch) - supply(last block) + burn in that first block; burnt = supply(first block) - supply(last block) + burn in the first block.",
            "code": "nut/rpc.py::fetch_epochs",
            "csv": "data/processed/epochs.csv",
        },
        {
            "id": "capture_monthly",
            "title": "3. Value capture vs issuance, by month",
            "sentence": (
                f"In {lm}, gas burn plus NEAR Intents revenue offset {fmt_pct(cap['last_full_month_coverage_total'])} of the NEAR minted "
                f"(burn {fmt_pct(cap['last_full_month_coverage_burn'])}, Intents {fmt_pct(cap['last_full_month_coverage_intents'])}); "
                f"in 2026 the monthly share ranged from {fmt_pct(cap['coverage_2026_min'])} to {fmt_pct(cap['coverage_2026_max'])}."
            ),
            "sources": [f"{NB}", LL_REV, f"{NB} (near_price, to convert USD revenue to NEAR)"],
            "method": "coverage = (beta * txn_fee_near + intents_revenue_usd / price) / minted_near, summed per calendar month.",
            "code": "nut/analysis.py::capture_section",
            "csv": "data/processed/value_capture_monthly.csv",
        },
    ]
    if off.get("available"):
        specs.append(
            {
                "id": "coverage_official",
                "title": "4. Reproducing the official revenue dashboard",
                "sentence": (
                    f"Across {off['months_compared']} complete months of 2026 our independent estimate differs from revenue.near.org by "
                    f"{off['mean_abs_diff_pp']:.1f} percentage points on average (largest gap {off['max_abs_diff_pp']:.1f} pp in {off['max_abs_diff_month']}); "
                    f"{off['months_within_5pp']} of {off['months_compared']} months are within 5 pp."
                ),
                "sources": [OFF, LL_REV, NB],
                "method": "Same coverage ratio as chart 3, compared month by month with the official 'Revenue as % of NEAR emissions' series. The official methodology is not published in machine-readable form, so differences are reported, not explained away.",
                "code": "nut/analysis.py::official_section",
                "csv": "data/processed/coverage_vs_official.csv",
            }
        )
    specs += [
        {
            "id": "usage",
            "title": "5. Usage: L1 activity fell while cross-chain volume grew",
            "sentence": (
                f"From Q1 2026 to the last 90 days, average daily L1 transactions changed {_signed(use['txns_change_q1_to_last90'])} and active accounts "
                f"{_signed(use['active_accounts_change_q1_to_last90'])}, while daily NEAR Intents volume changed {_signed(use['intents_volume_usd_change_q1_to_last90'])}."
            ),
            "sources": [f"{NB} (txns, active_accounts, txn_fee)", LL_VOL],
            "method": "Weekly sums (weekly mean for active accounts), each indexed to its Q1 2026 average = 100, log scale.",
            "code": "nut/charts.py::usage",
            "csv": "data/processed/daily.csv",
        },
        {
            "id": "capture_rate",
            "title": "6. How much of each Intents dollar NEAR keeps",
            "sentence": (
                f"NEAR's captured revenue rose from {cap['net_bps_first_value']:.1f} basis points of Intents volume in {cap['net_bps_first_month']} "
                f"to {cap['net_bps_last_value']:.1f} bps in {lm}, while gross fees stayed around {cap['d90']['gross_fee_bps']:.0f} bps (last 90 days)."
            ),
            "sources": [LL_VOL, LL_FEES, LL_REV],
            "method": "bps = 10,000 * monthly revenue (or gross fees) / monthly volume.",
            "code": "nut/analysis.py::capture_section",
            "csv": "data/processed/value_capture_monthly.csv",
        },
        {
            "id": "reflexivity",
            "title": "7. Revenue in USD vs revenue in NEAR",
            "sentence": (
                f"Average monthly Intents revenue in {cap['growth_to_months']} was {cap['revenue_usd_growth_multiple']:.1f}x its Q1 2026 level in USD but only "
                f"{cap['revenue_near_growth_multiple']:.1f}x in NEAR, because the NEAR price rose {cap['price_growth_multiple']:.1f}x; issuance is fixed in NEAR, so a higher price raises the bar."
            ),
            "sources": [LL_REV, NB],
            "method": "Monthly Intents revenue in USD, the same revenue divided by the daily NEAR price, and the monthly mean price, each divided by its Q1 2026 monthly average.",
            "code": "nut/charts.py::reflexivity",
            "csv": "data/processed/value_capture_monthly.csv",
        },
        {
            "id": "leadlag",
            "title": "8. Does anything lead? Lead-lag tests",
            "sentence": _leadlag_sentence(ll),
            "sources": [LL_VOL, NB],
            "method": f"Weekly log changes, {ll['weeks']} weeks from {ll['start_week']} to {ll['end_week']}. F-test of {ll['lags']} predictor lags added to an AR({ll['lags']}) model; p-value from all circular shifts of the predictor of at least 8 weeks; Holm correction across {ll['n_tests']} tests.",
            "code": "nut/leadlag.py",
            "csv": "data/processed/weekly_leadlag_inputs.csv",
        },
        {
            "id": "xcorr",
            "title": "9. Cross-correlations by lag",
            "sentence": (
                f"Same-week correlation between Intents volume growth and NEAR price returns is {ll['corr_same_week_intents_price']:.2f}; "
                + _xcorr_phrase(ll)
            ),
            "sources": [LL_VOL, NB],
            "method": "corr(x[t-k], y[t]) for k = -8..8 weeks; band = 95th percentile of |corr| over all circular shifts >= 8 weeks, pooled across lags.",
            "code": "nut/leadlag.py::xcorr",
            "csv": "data/processed/weekly_leadlag_inputs.csv",
        },
    ]
    if wal.get("available"):
        specs.append(
            {
                "id": "wallets",
                "title": "10. Where the bought-back NEAR sits",
                "sentence": _wallet_sentence(wal, m),
                "sources": ["archival JSON-RPC `query` view_account at sampled heights", LL_HREV],
                "method": "Native balance (amount + locked) of each wallet listed on revenue.near.org, sampled with the supply samples; DefiLlama holders revenue (USD) divided by the daily NEAR price and accumulated.",
                "code": "nut/rpc.py::fetch_wallet_balances",
                "csv": "data/processed/wallet_balances.csv",
            }
        )
    specs += [
        {
            "id": "breakeven",
            "title": "11. What it would take: break-even scenarios",
            "sentence": (
                f"At the last 90 days' capture rate ({be['net_capture_bps']:.1f} bps) and price, usage-based capture covers {fmt_pct(be['coverage_total_usd'])} of issuance in USD terms; "
                f"it must grow {be['multiple']:.1f}x, which means about {fmt_usd(be['required_daily_intents_volume_usd'])} of Intents volume per day "
                f"(now {fmt_usd(be['current_daily_intents_volume_usd'])}). Even at the launch-phase year-over-year volume growth ({fmt_pct(be['observed_growth_per_year'], 0)}) that takes "
                f"{be['years_at_observed_growth']:.1f} years with price and capture rate held constant; at 50% a year it takes {_years_at(be, 0.5)} years."
            ),
            "sources": ["charts 3 and 6", LL_VOL],
            "method": "multiple = sum(minted * price) / sum(burn * price + intents revenue) over 90 days; years = ln(multiple) / ln(1 + g). Scenarios, not forecasts.",
            "code": "nut/analysis.py::breakeven_section",
            "csv": "docs/metrics.json",
        },
        {
            "id": "data_checks",
            "title": "12. Data checks between independent sources",
            "sentence": (
                f"Monthly gas fees from DefiLlama (Allium) and NearBlocks differ by {_signed(chk['fees_ratio_last24_min'] - 1)} to {_signed(chk['fees_ratio_last24_max'] - 1)} over the last 24 months, "
                f"and the NearBlocks price is within {fmt_pct(chk['price_p95_abs_rel_diff'], 1)} of CoinGecko on 95% of {chk['price_days_compared']} days (a consistency check only: NearBlocks may source prices from CoinGecko)."
            ),
            "sources": [LL_CHAIN, NB, CG],
            "method": "Ratio of monthly fee sums; absolute relative price difference per day.",
            "code": "nut/analysis.py::data_checks_section",
            "csv": "data/processed/fees_cross_check_monthly.csv",
        },
    ]
    return specs


def _wallet_sentence(wal: dict, m: dict) -> str:
    rows = {r["account_id"]: r for r in wal.get("wallet_summary", [])}
    bb = rows.get("buybacks.multisignature.near")
    parts = [
        f"Revenue wallets listed on revenue.near.org hold native NEAR (nothing is burned): buybacks.multisignature.near held "
        f"{fmt_near(wal['buyback_wallet_latest_near'])} on {wal['buyback_wallet_latest_time']}"
        + (f" (first sample above 10K NEAR: {bb['first_sample_over_10k']})" if bb and bb["first_sample_over_10k"] else "")
    ]
    for acc, r in rows.items():
        if acc == "buybacks.multisignature.near":
            continue
        parts.append(
            f"{acc} held {fmt_near(r['latest_near'])}"
            + (f" (above 10K NEAR since the {r['first_sample_over_10k']} sample)" if r["first_sample_over_10k"] else "")
        )
    start = m.get("capture", {}).get("since_buyback", {}).get("start", "the program start")
    return "; ".join(parts) + f". DefiLlama attributes {fmt_near(wal['defillama_buyback_near_same_period'])} of buybacks to the period since {start}."


def _years_at(be: dict, g: float) -> str:
    for r in be["scenarios"]:
        if abs(r["growth_per_year"] - g) < 1e-9 and r["years_to_breakeven"] is not None:
            return f"{r['years_to_breakeven']:.1f}"
    return "n/a"


def _leadlag_sentence(ll: dict) -> str:
    sig = [t for t in ll["tests"] if t["significant"]]
    base = f"{len(sig)} of {ll['n_tests']} lead-lag tests pass the Holm-adjusted 5% threshold over {ll['weeks']} weeks"
    if sig:
        names = ", ".join(f"{t['predictor']} -> {t['target']}" for t in sig)
        return base + f" ({names}); " + _h2_phrase(ll)
    return base + f" ({ll['n_raw_below_alpha']} pass before correction); " + _h2_phrase(ll)


def _h2_phrase(ll: dict) -> str:
    n = ll["h2_intents_better_count"]
    return f"Intents volume explains more of next weeks' L1 usage than price does for {n} of 3 usage metrics."


def _xcorr_phrase(ll: dict) -> str:
    parts = []
    names = {"intents_to_price": "Intents->price", "intents_to_gas": "Intents->gas", "price_to_gas": "price->gas"}
    for k, label in names.items():
        xc = ll["xcorr"][k]
        n_out = sum(1 for lag, c in zip(xc["lags"], xc["corr"]) if lag != 0 and abs(c) > xc["band95"])
        parts.append(f"{label}: {n_out} of {len(xc['lags']) - 1} non-zero lags outside the 95% band")
    return "; ".join(parts) + "."
