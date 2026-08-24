"""Command-line interface for Bedding Order Parser."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.pipeline.order_parser import parse_order


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bedding_order_parser")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser(
        "parse",
        help="Parse a PI Excel file into the final duvet-cover JSON format.",
    )
    parse_parser.add_argument("input_excel", type=Path)
    parse_parser.add_argument("--output", required=True, type=Path)
    parse_parser.add_argument(
        "--dictionary-validate",
        action="store_true",
        help="Write a validation-only product dictionary report.",
    )
    parse_parser.add_argument("--overwrite", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse":
        try:
            summary = parse_order(
                input_path=args.input_excel,
                output_path=args.output,
                overwrite=args.overwrite,
                dictionary_validate=args.dictionary_validate,
            )
        except BeddingOrderParserError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        print(f"Input: {summary.input_file_name}")
        print(f"Records: {summary.record_count}")
        print(f"Result JSON: {summary.output_path}")
        print(f"Parse report JSON: {summary.report_path}")
        print(f"Warnings: {summary.warning_count}")
        if summary.validation_report_path:
            print(f"Dictionary validation JSON: {summary.validation_report_path}")
            print(f"Dictionary validation status: {summary.validation_status}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
