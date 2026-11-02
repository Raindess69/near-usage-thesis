"""Offline build: data/raw -> data/processed/*.csv, docs/metrics.json, docs/charts/*, docs/index.html, THESIS.md."""
from __future__ import annotations

import shutil

import pandas as pd

from . import analysis, charts, dashboard, load, narrative, thesis
from .config import Paths, load_config
from .util import read_json, write_json


def compute(paths: Paths) -> tuple[dict, dict]:
    """Return (metrics, tables). `metrics` is JSON-ready; `tables` holds DataFrames for charts/CSVs."""
    cfg = load_config(paths.root)
    manifest = read_json(paths.raw / "manifest.json")
    d = load.daily(paths)
    ep = load.rpc_epochs(paths)
    samples = load.rpc_supply_samples(paths)
    wallets = load.rpc_wallets(paths)
    official = load.official_dashboard(paths)
    pconf = load.rpc_protocol_config(paths)

    as_of = analysis.as_of_date(d, manifest["fetched_at"])
    iss = analysis.issuance_section(d, ep, samples, as_of)
    cap = analysis.capture_section(d, iss["_minted_daily"], iss["burn_to_fee_ratio"], as_of, cfg)
    off = analysis.official_section(official, cap["_monthly"])
    use = analysis.usage_section(d, as_of)
    chk = analysis.data_checks_section(d, as_of)
    wal = analysis.wallets_section(wallets, cap["_daily"], cfg)
    be = analysis.breakeven_section(cap, use, cfg)
    ll = analysis.leadlag_section(d, as_of, cfg)

    num = lambda frac: [int(v) for v in frac]  # noqa: E731
    metrics = {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "fetched_at": manifest["fetched_at"],
        "protocol": {
            "protocol_version": pconf.get("protocol_version"),
            "max_inflation_rate": num(pconf["max_inflation_rate"]),
            "max_inflation_rate_float": pconf["max_inflation_rate"][0] / pconf["max_inflation_rate"][1],
            "protocol_reward_rate": num(pconf["protocol_reward_rate"]),
            "epoch_length_blocks": pconf.get("epoch_length"),
        },
        "issuance": iss,
        "capture": cap,
        "official": off,
        "usage": use,
        "checks": chk,
        "wallets": wal,
        "breakeven": be,
        "leadlag": ll,
    }
    tables = {
        "daily": d,
        "epochs": ep,
        "samples": samples,
        "wallets": wallets,
        "capture_daily": cap["_daily"],
        "monthly": cap["_monthly"],
        "official": off.get("_table"),
        "weekly": ll["_weekly"],
        "fees_monthly": chk["_fees_monthly"],
        "price_check": chk["_price"],
        "gross_rate_7d": iss["_gross_rate_7d"],
    }
    return analysis.strip_private(metrics), {"tables": tables, "raw_sections": {"issuance": iss, "leadlag": ll, "breakeven": be, "cfg": cfg}}


def write_processed(paths: Paths, tables: dict) -> None:
    p = paths.processed
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True)
    t = tables
    t["daily"].loc["2020-07-21":].to_csv(p / "daily.csv", float_format="%.10g")
    t["capture_daily"].loc["2025-01-01":].to_csv(p / "value_capture_daily.csv", float_format="%.10g")
    t["monthly"].to_csv(p / "value_capture_monthly.csv", float_format="%.10g")
    t["epochs"][["epoch_start_height", "epoch_end_height", "start", "next_start", "duration_s", "minted_near", "burnt_near", "supply_end_near", "annualized_issuance"]].to_csv(p / "epochs.csv", index=False, float_format="%.10g")
    t["samples"][["height", "time", "total_supply_near"]].to_csv(p / "supply_samples.csv", index=False, float_format="%.12g")
    t["wallets"][["account_id", "height", "time", "balance_near", "exists"]].to_csv(p / "wallet_balances.csv", index=False, float_format="%.10g")
    t["weekly"].to_csv(p / "weekly_leadlag_inputs.csv", float_format="%.10g")
    t["fees_monthly"].to_csv(p / "fees_cross_check_monthly.csv", float_format="%.10g")
    if t["official"] is not None:
        t["official"].to_csv(p / "coverage_vs_official.csv", float_format="%.10g")


def render_charts(paths: Paths, metrics: dict, extra: dict) -> None:
    out = paths.charts
    if out.exists():
        shutil.rmtree(out)
    t = extra["tables"]
    iss = extra["raw_sections"]["issuance"]
    as_of = pd.Timestamp(metrics["as_of"])
    cfg = extra["raw_sections"]["cfg"]
    charts.issuance(out, t["daily"], iss, t["samples"], as_of)
    charts.epochs(out, t["epochs"])
    charts.capture_monthly(out, t["monthly"])
    if t["official"] is not None:
        charts.coverage_official(out, t["official"])
    charts.usage(out, t["daily"], as_of)
    charts.capture_rate(out, t["monthly"])
    charts.leadlag_chart(out, metrics["leadlag"])
    charts.xcorr_chart(out, metrics["leadlag"])
    charts.reflexivity(out, t["monthly"], metrics["capture"].get("growth_from_month", "2026-02"))
    charts.wallets(out, t["wallets"], t["capture_daily"], cfg["analysis"]["buyback_program_start"])
    charts.breakeven(out, metrics["breakeven"])
    charts.data_checks(out, t["fees_monthly"], t["price_check"])


def update_readme(paths: Paths, m: dict) -> None:
    """Refresh the computed results block in README.md between the RESULTS markers."""
    readme = paths.root / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    if start not in text or end not in text:
        return
    v = thesis.values(m)
    block = (
        f"{start}\n"
        f"**Result (data as of {v['as_of']}, generated by `make build`):**\n\n"
        f"- NEAR mints **{v['rpc_issuance']}** of supply per year ({v['rpc_minted_day']} per day), measured from block headers over {v['rpc_epochs']} epochs.\n"
        f"- Gas burn offsets **{v['rpc_burn_over_mint']}** of that. L1 transaction counts do not matter for supply.\n"
        f"- NEAR Intents revenue, used for buybacks since {v['sb_start']}, offset **{v['d90_cov_int']}** over the last 90 days: {v['d90_rev_over_gas']} the chain's gas fees.\n"
        f"- Together, usage paid for **{v['d90_cov']}** of issuance over 90 days and **{v['ytd_cov']}** year to date (official dashboard: {v.get('off_ytd', 'n/a')}).\n"
        f"- To cover issuance at today's price, usage-based revenue must grow **{v['be_multiple']}** (about {v['be_req_day']} of Intents volume per day, now {v['be_cur_day']}).\n"
        f"- Lead-lag: **{v['ll_sig']} of {v['ll_n']}** weekly tests (usage vs price, Intents vs L1 usage) are significant after Holm correction.\n"
        f"{end}"
    )
    i, j = text.index(start), text.index(end) + len(end)
    readme.write_text(text[:i] + block + text[j:], encoding="utf-8")


def run(paths: Paths, log=print) -> dict:
    log("build: computing metrics from data/raw/")
    metrics, extra = compute(paths)
    write_processed(paths, extra["tables"])
    log("build: rendering charts")
    render_charts(paths, metrics, extra)
    specs = narrative.chart_specs(metrics)
    metrics["charts"] = [{k: v for k, v in s.items() if k in ("id", "title", "sentence")} for s in specs]
    write_json(paths.docs / "metrics.json", metrics)
    log("build: writing docs/index.html and THESIS.md")
    dashboard.write(paths, metrics, specs)
    thesis.write(paths, metrics)
    update_readme(paths, metrics)
    log(f"build: as-of {metrics['as_of']}; {len(specs)} charts")
    return metrics
