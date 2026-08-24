"""Standalone CLI for read-only dictionary previews and shadow comparison."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from bedding_order_parser.dictionaries.integration_preview import (
    load_and_build_integration_preview,
    write_integration_preview,
)
from bedding_order_parser.dictionaries.loader import load_dictionary_bundle
from bedding_order_parser.dictionaries.shadow_matcher import build_shadow_report
from bedding_order_parser.dictionaries.shadow_writer import write_shadow_report
from bedding_order_parser.dictionaries.writer import write_dictionary_preview
from bedding_order_parser.exceptions import BeddingOrderParserError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m bedding_order_parser.dictionaries")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview_parser = subparsers.add_parser(
        "build-preview",
        help="Build a normalized JSON preview from approved dictionary workbooks.",
    )
    preview_parser.add_argument("--rules", required=True, type=Path)
    preview_parser.add_argument("--styles", required=True, type=Path)
    preview_parser.add_argument("--output", required=True, type=Path)
    preview_parser.add_argument("--overwrite", action="store_true")

    shadow_parser = subparsers.add_parser(
        "shadow-compare",
        help="Build an independent dictionary shadow comparison report.",
    )
    shadow_parser.add_argument("--input-dir", required=True, type=Path)
    shadow_parser.add_argument("--results-dir", required=True, type=Path)
    shadow_parser.add_argument("--reports-dir", required=True, type=Path)
    shadow_parser.add_argument("--rules", required=True, type=Path)
    shadow_parser.add_argument("--styles", required=True, type=Path)
    shadow_parser.add_argument("--output", required=True, type=Path)
    shadow_parser.add_argument("--overwrite", action="store_true")

    integration_parser = subparsers.add_parser(
        "integration-preview",
        help="Simulate dictionary integration decisions from a shadow report.",
    )
    integration_parser.add_argument("--shadow-report", required=True, type=Path)
    integration_parser.add_argument("--output", required=True, type=Path)
    integration_parser.add_argument("--overwrite", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build-preview":
        try:
            bundle = load_dictionary_bundle(args.rules, args.styles)
            output_path = write_dictionary_preview(
                bundle,
                args.output,
                overwrite=args.overwrite,
            )
        except BeddingOrderParserError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        print(f"Dictionary preview JSON: {output_path}")
        print(f"Rule rows: {bundle.summary['rule_rows']}")
        print(f"Fabric rows: {bundle.summary['fabric_rows']}")
        print(f"Style rows: {bundle.summary['style_rows']}")
        return 0

    if args.command == "shadow-compare":
        try:
            report = build_shadow_report(
                input_dir=args.input_dir,
                results_dir=args.results_dir,
                reports_dir=args.reports_dir,
                rules_path=args.rules,
                styles_path=args.styles,
            )
            output_path = write_shadow_report(
                report,
                args.output,
                overwrite=args.overwrite,
            )
        except BeddingOrderParserError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        print(f"Dictionary shadow report JSON: {output_path}")
        print(f"Files: {report.summary['file_count']}")
        print(f"Records: {report.summary['record_count']}")
        return 0

    if args.command == "integration-preview":
        try:
            preview = load_and_build_integration_preview(args.shadow_report)
            output_path = write_integration_preview(
                preview,
                args.output,
                overwrite=args.overwrite,
            )
        except BeddingOrderParserError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        summary = preview["summary"]
        print(f"Dictionary integration preview JSON: {output_path}")
        print(f"Files: {summary['file_count']}")
        print(f"Records: {summary['record_count']}")
        print(f"Evaluated fields: {summary['evaluated_field_count']}")
        print(f"Proposed changes: {summary['proposed_change_count']}")
        print(f"Manual reviews: {summary['manual_review_count']}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
