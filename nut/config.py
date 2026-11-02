"""Load config.toml and resolve project paths."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def raw_http(self) -> Path:
        return self.raw / "http"

    @property
    def raw_rpc(self) -> Path:
        return self.raw / "rpc"

    @property
    def processed(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def docs(self) -> Path:
        return self.root / "docs"

    @property
    def charts(self) -> Path:
        return self.docs / "charts"

    @property
    def thesis_template(self) -> Path:
        return self.root / "thesis" / "THESIS.template.md"

    @property
    def thesis(self) -> Path:
        return self.root / "THESIS.md"


def load_config(root: Path | None = None) -> dict:
    root = root or ROOT
    with open(root / "config.toml", "rb") as fh:
        cfg = tomllib.load(fh)
    env_rpc = os.environ.get("NEAR_ARCHIVAL_RPC")
    if env_rpc:
        cfg["rpc"]["urls"] = [u.strip() for u in env_rpc.split(",") if u.strip()]
    return cfg
