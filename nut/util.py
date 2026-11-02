"""Small shared helpers."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

YOCTO = 10**24


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, obj, indent: int | None = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=indent, sort_keys=False, ensure_ascii=False, default=_json_default)
        fh.write("\n")


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _json_default(o):
    # numpy / pandas scalars
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(f"not JSON serializable: {type(o)}")


def clean_number(x):
    """Turn NaN/inf into None so metrics.json stays valid JSON."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(xf) or math.isinf(xf):
        return None
    return xf


def fmt_pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def fmt_usd(x: float) -> str:
    ax = abs(x)
    if ax >= 1e9:
        return f"${x / 1e9:.2f}B"
    if ax >= 1e6:
        return f"${x / 1e6:.2f}M"
    if ax >= 1e3:
        return f"${x / 1e3:.1f}K"
    return f"${x:,.0f}"


def fmt_near(x: float) -> str:
    ax = abs(x)
    if ax >= 1e9:
        return f"{x / 1e9:.3f}B NEAR"
    if ax >= 1e6:
        return f"{x / 1e6:.2f}M NEAR"
    if ax >= 1e3:
        return f"{x / 1e3:.1f}K NEAR"
    return f"{x:,.0f} NEAR"


def fmt_mult(x: float) -> str:
    return f"{x:.1f}x"
