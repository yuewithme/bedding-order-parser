"""CLI for canonical material stores, vector indexes, matching, and review workbooks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.materials.hybrid_matcher import match_orders
from bedding_order_parser.materials.match_writer import write_match_outputs
from bedding_order_parser.materials.review_validator import validate_review_workbook
from bedding_order_parser.materials.review_workbook import build_review_workbook
from bedding_order_parser.materials.store import build_material_store
from bedding_order_parser.materials.vector_index import build_vector_indexes
from bedding_order_parser.materials.vector_search import search_vector_index


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m bedding_order_parser.materials")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build material SQLite and JSONL store.")
    build.add_argument("--source", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--overwrite", action="store_true")

    build_index = subparsers.add_parser(
        "build-index", help="Build full and duvet-cover FAISS indexes."
    )
    build_index.add_argument("--documents", required=True, type=Path)
    build_index.add_argument("--store", required=True, type=Path)
    build_index.add_argument("--output-dir", required=True, type=Path)
    build_index.add_argument("--model", default="BAAI/bge-m3")
    build_index.add_argument("--device", default="cpu")
    build_index.add_argument("--batch-size", type=int, default=16)
    build_index.add_argument("--overwrite", action="store_true")

    search = subparsers.add_parser(
        "search-index", help="Search a material FAISS index."
    )
    search.add_argument("--index-dir", required=True, type=Path)
    search.add_argument("--scope", choices=("all", "duvet_cover"), default="duvet_cover")
    search.add_argument("--query", required=True)
    search.add_argument("--top-k", type=int, default=10)

    match = subparsers.add_parser(
        "match-orders", help="Run the manual-review-only hybrid matching prototype."
    )
    match.add_argument("--orders-dir", required=True, type=Path)
    match.add_argument("--parse-reports-dir", required=True, type=Path)
    match.add_argument("--store", required=True, type=Path)
    match.add_argument("--index-dir", required=True, type=Path)
    match.add_argument("--output-dir", required=True, type=Path)
    match.add_argument("--top-k", type=int, default=10)
    match.add_argument("--vector-recall-k", type=int, default=300)
    match.add_argument("--overwrite", action="store_true")

    build_review = subparsers.add_parser(
        "build-review", help="Build the material matching human review workbook."
    )
    build_review.add_argument("--candidates", required=True, type=Path)
    build_review.add_argument("--summary", required=True, type=Path)
    build_review.add_argument("--store", required=True, type=Path)
    build_review.add_argument("--output", required=True, type=Path)
    build_review.add_argument("--overwrite", action="store_true")

    validate_review = subparsers.add_parser(
        "validate-review", help="Validate a filled material matching review workbook."
    )
    validate_review.add_argument("--workbook", required=True, type=Path)
    validate_review.add_argument("--store", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_material_store(
                args.source, args.output_dir, overwrite=args.overwrite
            )
            print(f"Source: {result.source_audit.path}")
            print(f"Source SHA-256: {result.source_audit.sha256}")
            print(f"Records: {result.source_audit.row_count}")
            print(f"SQLite: {result.sqlite_path} ({result.sqlite_records})")
            print(f"JSONL: {result.jsonl_path} ({result.jsonl_records})")
            print(f"Manifest: {result.manifest_path}")
            print(f"Elapsed seconds: {result.elapsed_seconds:.3f}")
            return 0

        if args.command == "build-index":
            result = build_vector_indexes(
                args.documents,
                args.store,
                args.output_dir,
                model_name=args.model,
                device=args.device,
                batch_size=args.batch_size,
                overwrite=args.overwrite,
            )
            print(f"Model: {result.manifest['model']['name']}")
            print(f"Revision: {result.manifest['model']['revision']}")
            print(f"Dimension: {result.dimension}")
            print(f"All records: {result.all_records}")
            print(f"Duvet-cover records: {result.duvet_cover_records}")
            print(f"Manifest: {result.manifest_path}")
            print(f"Elapsed seconds: {result.duration_seconds:.3f}")
            return 0

        if args.command == "search-index":
            results = search_vector_index(
                args.index_dir,
                args.query,
                scope=args.scope,
                top_k=args.top_k,
            )
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return 0

        if args.command == "match-orders":
            result = match_orders(
                args.orders_dir,
                args.parse_reports_dir,
                args.store,
                args.index_dir,
                top_k=args.top_k,
                vector_recall_k=args.vector_recall_k,
            )
            outputs = write_match_outputs(
                result, args.output_dir, overwrite=args.overwrite
            )
            summary = result.summary_payload["summary"]
            print(f"Order records: {summary['order_records']}")
            print(f"Records with candidates: {summary['records_with_candidates']}")
            print(f"Candidates: {outputs.candidates_path}")
            print(f"Summary: {outputs.summary_path}")
            return 0

        if args.command == "build-review":
            result = build_review_workbook(
                args.candidates,
                args.summary,
                args.store,
                args.output,
                overwrite=args.overwrite,
            )
            print(f"Review records: {result.review_records}")
            print(f"Recommended codes: {result.recommended_codes}")
            print(f"No candidate: {result.no_candidate}")
            print(f"Ambiguous tie: {result.ambiguous_tie}")
            print(f"Insufficient evidence: {result.insufficient_evidence}")
            print(f"Unique best candidate: {result.unique_best_candidate}")
            print(f"Candidate detail rows: {result.candidate_detail_rows}")
            print(f"Workbook: {result.output_path}")
            return 0

        if args.command == "validate-review":
            result = validate_review_workbook(args.workbook, args.store)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            return 0 if result.ok else 1
    except BeddingOrderParserError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
