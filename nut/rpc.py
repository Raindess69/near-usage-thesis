"""Minimal NEAR JSON-RPC client plus the three onchain measurements used by the thesis.

1. Epoch accounting: for each complete epoch, the NEAR minted at the next epoch boundary and the
   NEAR burnt inside the epoch, both read from `total_supply` in block headers.
2. Supply samples: one block header every N heights since genesis (cross-checks the indexer).
3. Wallet balances: native NEAR balance of revenue/buyback wallets at sampled heights.
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

UNKNOWN_MARKERS = ("UNKNOWN_BLOCK", "DB Not Found", "NOT_SYNCED_YET", "doesn't exist", "UNKNOWN_EPOCH")


class RpcError(RuntimeError):
    pass


class Rpc:
    """JSON-RPC client with a shared request throttle and fallback endpoints (rotated on rate limits)."""

    def __init__(self, urls, timeout: float = 40.0, retries: int = 15, min_interval: float = 0.3, cache_path=None):
        self.urls = [urls] if isinstance(urls, str) else list(urls)
        self.cache_path = cache_path
        self.cache = {}
        if cache_path is not None and os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        k, v = json.loads(line)
                        self.cache[k] = v
                    except ValueError:
                        continue
        self.url_idx = 0
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "near-usage-thesis/1.0"
        self.calls = 0
        self._lock = threading.Lock()
        self._next_slot = 0.0

    @property
    def url(self) -> str:
        return self.urls[self.url_idx]

    def _throttle(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self.min_interval
        if wait > 0:
            time.sleep(wait)

    def _rotate(self) -> None:
        with self._lock:
            self.url_idx = (self.url_idx + 1) % len(self.urls)
            # back off: slow the shared request rate after every rate-limit response
            self.min_interval = min(6.0, self.min_interval * 1.5 + 0.2)

    def _relax(self) -> None:
        with self._lock:
            self.min_interval = max(0.3, self.min_interval * 0.97)

    def _cache_key(self, method: str, params):
        if isinstance(params, dict) and params.get("finality"):
            return None
        if method not in ("block", "query"):
            return None
        return method + ":" + json.dumps(params, sort_keys=True)

    def _cache_put(self, key, value) -> None:
        if key is None or self.cache_path is None:
            return
        with self._lock:
            self.cache[key] = value
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps([key, value]) + "\n")

    def call(self, method: str, params):
        """Return `result`, or None when the node reports an unknown block/account."""
        key = self._cache_key(method, params)
        if key is not None and key in self.cache:
            return self.cache[key]
        res = self._call(method, params)
        self._cache_put(key, res)
        return res

    def _call(self, method: str, params):
        last = None
        for attempt in range(self.retries):
            self._throttle()
            url = self.url
            try:
                self.calls += 1
                r = self.session.post(
                    url,
                    json={"jsonrpc": "2.0", "id": "nut", "method": method, "params": params},
                    timeout=self.timeout,
                )
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"HTTP {r.status_code} from {url}"
                    self._rotate()
                    time.sleep(min(20, 1 + attempt))
                    continue
                j = r.json()
            except (requests.RequestException, ValueError) as exc:
                last = repr(exc)
                self._rotate()
                time.sleep(min(30, 2 * (attempt + 1)))
                continue
            if "result" in j:
                self._relax()
                res = j["result"]
                if isinstance(res, dict) and "error" in res and any(m in str(res["error"]) for m in UNKNOWN_MARKERS):
                    return None
                return res
            err = json.dumps(j.get("error", j))
            if "-429" in err or "Rate limit" in err:
                last = f"rate limited by {url}"
                self._rotate()
                time.sleep(min(20, 1 + attempt))
                continue
            if "GARBAGE_COLLECTED" in err:
                last = f"{url} is not archival"
                self._rotate()
                continue
            if any(m in err for m in UNKNOWN_MARKERS) or "UNKNOWN_ACCOUNT" in err:
                return None
            last = err[:300]
            time.sleep(min(30, 2 * (attempt + 1)))
        raise RpcError(f"{method} failed after {self.retries} attempts: {last}")

    # -- typed helpers -------------------------------------------------------------------------
    def block(self, height: int | None = None, block_hash: str | None = None, finality: str | None = None):
        if finality:
            return self.call("block", {"finality": finality})
        if block_hash:
            return self.call("block", {"block_id": block_hash})
        return self.call("block", {"block_id": int(height)})

    def block_at_or_after(self, height: int, max_skip: int = 200):
        for k in range(max_skip):
            b = self.block(height + k)
            if b is not None:
                return b
        raise RpcError(f"no block found in [{height}, {height + max_skip})")

    def view_account(self, account_id: str, block_height: int):
        return self.call(
            "query",
            {"request_type": "view_account", "block_id": int(block_height), "account_id": account_id},
        )

    def protocol_config(self):
        return self.call("EXPERIMENTAL_protocol_config", {"finality": "final"})


def _header_summary(b: dict) -> dict:
    h = b["header"]
    height = int(h["height"])
    # Only chunks produced in this block carry this block's burn; old headers are repeated for missing chunks.
    burnt = sum(int(c.get("balance_burnt", 0)) for c in b.get("chunks", []) if int(c.get("height_included", -1)) == height)
    return {
        "height": height,
        "hash": h["hash"],
        "prev_hash": h["prev_hash"],
        "timestamp_ns": int(h["timestamp_nanosec"]),
        "total_supply": h["total_supply"],
        "gas_price": h["gas_price"],
        "balance_burnt_in_block": str(burnt),
        "epoch_id": h["epoch_id"],
        "next_epoch_id": h["next_epoch_id"],
    }


def fetch_epochs(rpc: Rpc, n_epochs: int, log=print) -> list[dict]:
    """Walk back `n_epochs` complete epochs from the current one, using only `block` calls.

    In every block header, `next_epoch_id` is the hash of the last block of the previous epoch, so
    the chain of epoch-end blocks can be followed by hash. The first block of an epoch is the next
    existing height after the previous epoch's last block. For epoch E with first block s(E), last block e(E):
      minted(E) = supply[s(E+1)] - supply[e(E)] + burnt_in_block[s(E+1)]   (reward minted at the next boundary)
      burnt(E)  = supply[s(E)]   - supply[e(E)] + burnt_in_block[s(E)]     (supply only falls inside an epoch)
    """
    head = _header_summary(rpc.block(finality="final"))
    ends = [_header_summary(rpc.block(block_hash=head["next_epoch_id"]))]  # last block of epoch T-1
    for i in range(n_epochs):
        ends.append(_header_summary(rpc.block(block_hash=ends[-1]["next_epoch_id"])))
        if (i + 1) % 20 == 0:
            log(f"  rpc epoch ends: {i + 1}/{n_epochs}")
    starts = [_header_summary(rpc.block_at_or_after(e["height"] + 1)) for e in ends]  # starts[i] follows ends[i]
    out = []
    # epoch E_i spans starts[i+1] .. ends[i]; its reward is minted in starts[i]
    for i in range(n_epochs):
        start, end, next_start = starts[i + 1], ends[i], starts[i]
        minted = int(next_start["total_supply"]) - int(end["total_supply"]) + int(next_start["balance_burnt_in_block"])
        burnt = int(start["total_supply"]) - int(end["total_supply"]) + int(start["balance_burnt_in_block"])
        out.append(
            {
                "epoch_start_height": start["height"],
                "epoch_end_height": end["height"],
                "next_epoch_start_height": next_start["height"],
                "start_timestamp_ns": start["timestamp_ns"],
                "end_timestamp_ns": end["timestamp_ns"],
                "next_start_timestamp_ns": next_start["timestamp_ns"],
                "supply_at_start_yocto": start["total_supply"],
                "supply_at_end_yocto": end["total_supply"],
                "supply_at_next_start_yocto": next_start["total_supply"],
                "burnt_in_start_block_yocto": start["balance_burnt_in_block"],
                "burnt_in_next_start_block_yocto": next_start["balance_burnt_in_block"],
                "minted_for_epoch_yocto": str(minted),
                "burnt_in_epoch_yocto": str(burnt),
            }
        )
    return out


def fetch_supply_samples(rpc: Rpc, genesis_height: int, step: int, parallel: int = 4, log=print) -> list[dict]:
    latest = _header_summary(rpc.block(finality="final"))
    heights = list(range(genesis_height + 1, latest["height"], step))

    def one(h):
        return _header_summary(rpc.block_at_or_after(h))

    with ThreadPoolExecutor(max_workers=parallel) as ex:
        rows = list(ex.map(one, heights))
    rows.append(latest)
    log(f"  rpc supply samples: {len(rows)}")
    return [{k: r[k] for k in ("height", "timestamp_ns", "total_supply", "gas_price")} for r in rows]


def fetch_wallet_balances(rpc: Rpc, accounts: list[str], samples: list[dict], from_ns: int, parallel: int = 4, log=print):
    heights = [s for s in samples if s["timestamp_ns"] >= from_ns]
    jobs = [(a, s) for a in accounts for s in heights]

    def one(job):
        account, s = job
        res = rpc.view_account(account, s["height"])
        amount = "0" if res is None else res["amount"]
        locked = "0" if res is None else res["locked"]
        return {"account_id": account, "height": s["height"], "timestamp_ns": s["timestamp_ns"],
                "amount_yocto": amount, "locked_yocto": locked, "exists": res is not None}

    with ThreadPoolExecutor(max_workers=parallel) as ex:
        rows = list(ex.map(one, jobs))
    log(f"  rpc wallet balances: {len(rows)}")
    return rows
