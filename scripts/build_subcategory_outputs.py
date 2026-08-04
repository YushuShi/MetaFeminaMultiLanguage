#!/usr/bin/env python3
"""Build offline subtype result JSON and plot artifacts from saved annotations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from subcategory_analysis import (  # noqa: E402
    DEFAULT_ANNOTATIONS,
    DEFAULT_CACHE_ROOT,
    DEFAULT_PLOT_ROOT,
    DEFAULT_REGISTRY_CSV,
    DEFAULT_RESULTS_ROOT,
    build_subcategory_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--plot-root", type=Path, default=DEFAULT_PLOT_ROOT)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY_CSV)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    args = parser.parse_args()
    if not args.annotations.is_file():
        print(f"No build performed: saved annotations not found at {args.annotations}", file=sys.stderr)
        return 2
    manifest = build_subcategory_outputs(
        args.annotations, args.results_root, args.plot_root, args.registry_csv, args.cache_root
    )
    print(f"Built {manifest['result_count']} subtype exposure result(s) from {manifest['eligible_estimate_count']} eligible estimate(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
