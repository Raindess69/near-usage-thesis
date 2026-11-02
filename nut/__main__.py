"""Command line: python -m nut {fetch,build,all,verify}."""
from __future__ import annotations

import argparse
import sys
import time

from .config import ROOT, Paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m nut", description="NEAR usage thesis pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download fresh raw data into data/raw/")
    f.add_argument("--skip-rpc", action="store_true", help="only refresh HTTP sources; keep the RPC snapshot")
    sub.add_parser("build", help="rebuild processed data, charts, dashboard and THESIS.md from data/raw/ (offline)")
    a = sub.add_parser("all", help="fetch + build")
    a.add_argument("--skip-rpc", action="store_true")
    sub.add_parser("verify", help="rebuild into a temp dir and check committed outputs match")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:  # pragma: no cover
        pass
    paths = Paths(ROOT)
    t0 = time.time()
    if args.cmd in ("fetch", "all"):
        from . import fetch

        fetch.run(paths, skip_rpc=args.skip_rpc)
    if args.cmd in ("build", "all"):
        from . import build

        build.run(paths)
    if args.cmd == "verify":
        from . import verify

        ok = verify.run(paths)
        print(f"done in {time.time() - t0:.1f}s")
        return 0 if ok else 1
    print(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
