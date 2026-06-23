#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse Rosatom procurement -> Fabrikant positions -> Excel rows."""
import argparse
import sys

from procurement.pipeline import export_rows, parse_rosatom_to_rows


def main():
    parser = argparse.ArgumentParser(description="Parse zakupki.rosatom.ru procurement")
    parser.add_argument(
        "--url",
        default="https://zakupki.rosatom.ru/2211291065696?link=procurements_archive&obj_id=2211291065696",
        help="Rosatom procurement URL",
    )
    parser.add_argument("--out", default="output/parsed_procurement.xlsx")
    parser.add_argument("--no-headless", action="store_true")
    args = parser.parse_args()

    rows = parse_rosatom_to_rows(args.url, headless=not args.no_headless)
    export_rows(rows, args.out)
    print(f"Saved {len(rows)} rows -> {args.out}")
    if rows:
        print("Sample header:", {k: rows[0].get(k) for k in (
            "rosatom_number", "status", "price_rub", "organizer", "etp_url"
        )})
    return 0


if __name__ == "__main__":
    sys.exit(main())
