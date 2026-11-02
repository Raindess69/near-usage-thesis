"""Parse data/raw/ into tidy pandas tables. No network access happens here."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Paths
from .util import YOCTO, read_json


def _day(ts) -> pd.Timestamp:
    return pd.Timestamp(ts).tz_localize(None).normalize() if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts).normalize()


def nearblocks_daily(paths: Paths) -> pd.DataFrame:
    rows = read_json(paths.raw_http / "nearblocks_charts.json")["charts"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None).dt.normalize()
    num = [c for c in df.columns if c != "date"]
    for c in num:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    out = pd.DataFrame(index=df.index)
    out["price_usd"] = df["near_price"].replace(0, np.nan)
    out["market_cap_usd"] = df["market_cap"].replace(0, np.nan)
    out["total_supply_near"] = df["total_supply"] / YOCTO
    out["circulating_supply_near"] = df["circulating_supply"] / YOCTO
    out["blocks"] = df["blocks"]
    out["txns"] = df["txns"]
    out["active_accounts"] = df["active_accounts"]
    out["new_accounts"] = df["new_accounts"]
    out["active_contracts"] = df["active_contracts"]
    out["gas_used"] = df["gas_used"]
    out["gas_fee_near"] = df["gas_fee"] / YOCTO
    out["txn_fee_near"] = df["txn_fee"] / YOCTO
    out["txn_fee_usd"] = df["txn_fee_usd"]
    return out


def llama_series(paths: Paths, name: str) -> pd.Series:
    j = read_json(paths.raw_http / f"{name}.json")
    pts = j["totalDataChart"]
    s = pd.Series({pd.Timestamp(int(t), unit="s").normalize(): float(v) for t, v in pts}, name=name)
    return s.sort_index()


def llama_meta(paths: Paths, name: str) -> dict:
    j = read_json(paths.raw_http / f"{name}.json")
    keep = ("name", "methodology", "methodologyURL", "total24h", "total7d", "total30d", "total1y", "totalAllTime")
    return {k: j.get(k) for k in keep if k in j}


def llama_tvl(paths: Paths) -> pd.Series:
    j = read_json(paths.raw_http / "llama_chain_tvl.json")
    s = pd.Series({pd.Timestamp(int(r["date"]), unit="s").normalize(): float(r["tvl"]) for r in j}, name="defi_tvl_usd")
    return s.sort_index()


def coingecko_price(paths: Paths) -> pd.Series:
    j = read_json(paths.raw_http / "coingecko_price.json")
    s = pd.Series({pd.Timestamp(int(ms), unit="ms").normalize(): float(p) for ms, p in j["prices"]}, name="cg_price_usd")
    return s[~s.index.duplicated(keep="first")].sort_index()


def nearblocks_stats(paths: Paths) -> dict:
    return read_json(paths.raw_http / "nearblocks_stats.json")["stats"][0]


def daily(paths: Paths) -> pd.DataFrame:
    """One row per UTC day with every series used by the analysis."""
    d = nearblocks_daily(paths)
    for col, name in [
        ("intents_volume_usd", "llama_intents_volume"),
        ("intents_fees_usd", "llama_intents_fees"),
        ("intents_revenue_usd", "llama_intents_revenue"),
        ("intents_buyback_usd", "llama_intents_holders_revenue"),
        ("llama_chain_fees_usd", "llama_chain_fees"),
    ]:
        d = d.join(llama_series(paths, name).rename(col), how="outer")
    d = d.join(llama_tvl(paths), how="outer").join(coingecko_price(paths), how="outer")
    d.index.name = "date"
    return d.sort_index()


# -- RPC snapshot ---------------------------------------------------------------------------------

def _near(col: pd.Series) -> pd.Series:
    """yoctoNEAR strings (can exceed int64) -> float NEAR."""
    return col.map(lambda v: int(v) / YOCTO).astype(float)


def rpc_epochs(paths: Paths) -> pd.DataFrame:
    rows = read_json(paths.raw_rpc / "epochs.json")["data"]
    df = pd.DataFrame(rows)
    df["start"] = pd.to_datetime(df["start_timestamp_ns"], unit="ns")
    df["next_start"] = pd.to_datetime(df["next_start_timestamp_ns"], unit="ns")
    df["duration_s"] = (df["next_start_timestamp_ns"] - df["start_timestamp_ns"]) / 1e9
    df["minted_near"] = _near(df["minted_for_epoch_yocto"])
    df["burnt_near"] = _near(df["burnt_in_epoch_yocto"])
    df["supply_end_near"] = _near(df["supply_at_end_yocto"])
    df["annualized_issuance"] = df["minted_near"] / df["supply_end_near"] * (365 * 86400) / df["duration_s"]
    return df.sort_values("epoch_start_height").reset_index(drop=True)


def rpc_supply_samples(paths: Paths) -> pd.DataFrame:
    rows = read_json(paths.raw_rpc / "supply_samples.json")["data"]
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["timestamp_ns"], unit="ns")
    df["total_supply_near"] = _near(df["total_supply"])
    return df.sort_values("height").reset_index(drop=True)


def rpc_wallets(paths: Paths) -> pd.DataFrame:
    rows = read_json(paths.raw_rpc / "wallet_balances.json")["data"]
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["timestamp_ns"], unit="ns")
    df["balance_near"] = _near(df["amount_yocto"]) + _near(df["locked_yocto"])
    return df.sort_values(["account_id", "height"]).reset_index(drop=True)


def rpc_protocol_config(paths: Paths) -> dict:
    return read_json(paths.raw_rpc / "protocol_config.json")["data"]


# -- revenue.near.org snapshot --------------------------------------------------------------------

def official_dashboard(paths: Paths) -> dict:
    """Extract the series embedded in the revenue.near.org page (Next.js payload).

    Returns {} if the page layout changed; the analysis then reports the comparison as unavailable.
    """
    f = paths.raw_http / "revenue_dashboard.html"
    if not f.exists():
        return {}
    html = f.read_text(encoding="utf-8", errors="ignore")
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    try:
        payload = "".join(json.loads('"' + c + '"') for c in chunks)
    except json.JSONDecodeError:
        return {}
    dec = json.JSONDecoder()
    out = {}
    for key in ("emissionsMonthly", "absoluteRevEmissions"):
        i = payload.find(f'"{key}":[')
        if i < 0:
            continue
        try:
            arr, _ = dec.raw_decode(payload[i + len(key) + 3 :])
            out[key] = arr
        except json.JSONDecodeError:
            continue
    m = re.search(r"Updated · ([A-Z][a-z]{2} \d{2}, \d{4})", re.sub(r"<[^>]+>", "", html))
    if m:
        out["updated"] = m.group(1)
    return out
