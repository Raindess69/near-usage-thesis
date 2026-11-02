"""Download every raw input into data/raw/ and record provenance in data/raw/manifest.json."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from .config import Paths, load_config
from .rpc import Rpc, fetch_epochs, fetch_supply_samples, fetch_wallet_balances
from .util import sha256_bytes, utc_now_iso, write_json

UA = {"User-Agent": "near-usage-thesis/1.0 (+https://github.com/Raindess69/near-usage-thesis)"}


def _get(url: str, retries: int = 5, timeout: float = 90.0) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code == 200 and r.content:
                return r.content
            last = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            last = repr(exc)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def fetch_http(paths: Paths, cfg: dict, log=print) -> dict:
    paths.raw_http.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name, url in cfg["sources"].items():
        ext = "html" if name == "revenue_dashboard" else "json"
        data = _get(url)
        out = paths.raw_http / f"{name}.{ext}"
        out.write_bytes(data)
        entries[f"http/{name}.{ext}"] = {"url": url, "fetched_at": utc_now_iso(), "bytes": len(data), "sha256": sha256_bytes(data)}
        log(f"  {name}: {len(data):,} bytes")
        time.sleep(0.5)
    return entries


def fetch_rpc(paths: Paths, cfg: dict, log=print) -> dict:
    rc = cfg["rpc"]
    rpc = Rpc(rc["urls"], cache_path=str(paths.root / ".cache" / "rpc_cache.jsonl"))
    entries = {}

    def save(name, obj, what):
        out = paths.raw_rpc / f"{name}.json"
        write_json(out, {"rpc_urls": rc["urls"], "fetched_at": utc_now_iso(), "what": what, "data": obj})
        data = out.read_bytes()
        entries[f"rpc/{name}.json"] = {"url": rc["urls"][0], "fetched_at": utc_now_iso(), "bytes": len(data), "sha256": sha256_bytes(data)}

    save("protocol_config", rpc.protocol_config(), "EXPERIMENTAL_protocol_config at final block")
    epochs = fetch_epochs(rpc, int(rc["epochs_back"]), log=log)
    save("epochs", epochs, "per-epoch minted and burnt NEAR from block-header total_supply")
    samples = fetch_supply_samples(rpc, int(rc["genesis_height"]), int(rc["supply_sample_step"]), int(rc["parallel_requests"]), log=log)
    save("supply_samples", samples, "block-header total_supply sampled every supply_sample_step heights")
    from_ns = int(datetime.fromisoformat(rc["wallets_from"]).replace(tzinfo=timezone.utc).timestamp() * 1e9)
    wallets = fetch_wallet_balances(rpc, list(rc["wallets"]), samples, from_ns, int(rc["parallel_requests"]), log=log)
    save("wallet_balances", wallets, "view_account native balance at sampled heights")
    log(f"  rpc calls made: {rpc.calls}")
    return entries


def run(paths: Paths, skip_rpc: bool = False, log=print) -> None:
    cfg = load_config(paths.root)
    manifest_path = paths.raw / "manifest.json"
    manifest = {"fetched_at": utc_now_iso(), "files": {}}
    if manifest_path.exists() and skip_rpc:
        from .util import read_json

        old = read_json(manifest_path)
        manifest["files"].update({k: v for k, v in old.get("files", {}).items() if k.startswith("rpc/")})
    log("fetch: HTTP sources")
    manifest["files"].update(fetch_http(paths, cfg, log=log))
    if not skip_rpc:
        log("fetch: NEAR RPC (archival)")
        manifest["files"].update(fetch_rpc(paths, cfg, log=log))
    manifest["files"] = dict(sorted(manifest["files"].items()))
    write_json(manifest_path, manifest)
    log(f"fetch: wrote {manifest_path.relative_to(paths.root)}")
