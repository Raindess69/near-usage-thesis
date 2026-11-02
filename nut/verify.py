"""Rebuild from data/raw/ into a temporary copy and compare with the committed outputs."""
from __future__ import annotations

import json
import math
import shutil
import tempfile
from pathlib import Path

from . import build
from .config import Paths

TRACKED = ["docs/metrics.json", "docs/index.html", "THESIS.md"]


def _close(a, b, path="") -> list[str]:
    errs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                errs.append(f"{path}/{k}: missing on one side")
            else:
                errs += _close(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            errs.append(f"{path}: length {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                errs += _close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        if a is None or b is None or not math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12):
            errs.append(f"{path}: {a} != {b}")
    elif a != b:
        errs.append(f"{path}: {a!r} != {b!r}")
    return errs


def run(paths: Paths) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp) / "repo"
        shutil.copytree(paths.root, tmp_root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".cache", "demo"))
        build.run(Paths(tmp_root), log=lambda *a: None)
        ok = True
        committed = json.loads((paths.root / "docs/metrics.json").read_text())
        rebuilt = json.loads((tmp_root / "docs/metrics.json").read_text())
        errs = _close(committed, rebuilt)
        if errs:
            ok = False
            print(f"verify: docs/metrics.json differs in {len(errs)} values, e.g.:")
            for e in errs[:10]:
                print("  ", e)
        else:
            print("verify: docs/metrics.json matches the rebuild")
        for rel in TRACKED[1:]:
            same = (paths.root / rel).read_text() == (tmp_root / rel).read_text()
            print(f"verify: {rel} {'matches' if same else 'DIFFERS from'} the rebuild")
            ok &= same
        charts_same = all(
            (paths.root / "docs/charts" / f.name).exists() and (paths.root / "docs/charts" / f.name).read_bytes() == f.read_bytes()
            for f in (tmp_root / "docs/charts").glob("*.svg")
        )
        print(f"verify: SVG charts {'match' if charts_same else 'differ (fonts or matplotlib version can change SVG bytes; numbers are what matter)'}")
        return ok
