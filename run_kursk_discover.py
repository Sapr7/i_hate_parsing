#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deep EIS discovery for Kursk AES (2020-2026)."""
import argparse
import sys
from pathlib import Path

from procurement.kursk_discover import discover_kursk_eis, save_kursk_discovery


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output/kursk_discovery_cache.json")
    ap.add_argument("--year-from", type=int, default=2020)
    ap.add_argument("--year-to", type=int, default=2026)
    ap.add_argument("--max-pages", type=int, default=25)
    args = ap.parse_args()

    print("Kursk EIS discovery", args.year_from, "-", args.year_to)
    by_reg, stats = discover_kursk_eis(
        year_from=args.year_from,
        year_to=args.year_to,
        max_pages_per_slice=args.max_pages,
    )
    out = Path(args.out)
    save_kursk_discovery(by_reg, stats, out)
    print("\nDONE", out, "notices:", stats["total_notices"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
