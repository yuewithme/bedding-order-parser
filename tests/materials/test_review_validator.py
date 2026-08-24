from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

from bedding_order_parser.materials.review_workbook import REVIEW_SHEET, build_review_workbook


def write_store(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE materials (
                material_code TEXT PRIMARY KEY,
                material_name_raw TEXT NOT NULL,
                spec_raw TEXT NOT NULL,
                color_raw TEXT NOT NULL,
                fabric_raw TEXT NOT NULL,
                composition_raw TEXT NOT NULL,
                style_raw TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO materials VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("MAT-1", "被套 A", "240*260cm", "漂白色", "贡缎", "C100", "无飞边"),
                ("MAT-2", "被套 B", "240*260cm", "漂白色", "贡缎", "C100", "无飞边"),
            ],
        )


def candidate(code: str) -> dict[str, object]:
    fields = {
        "spec": {"candidate_value": "240*260cm", "status": "exact_match"},
        "color": {"candidate_value": "漂白色", "status": "exact_match"},
        "fabric": {"candidate_value": "贡缎", "status": "equivalent_match"},
        "composition": {"candidate_value": "C100", "status": "exact_match"},
        "style": {"candidate_value": "无飞边", "status": "partial_match"},
        "label_method": {"candidate_value": "客标", "status": "no_match"},
        "size_type": {"candidate_value": "交货尺寸", "status": "missing_candidate"},
    }
    return {
        "rank": 1 if code == "MAT-1" else 2,
        "material_code": code,
        "prototype_match_score": 0.9,
        "structured_score": 0.8,
        "vector_score": 0.7,
        "duplicate_group_size": 1,
        "ambiguous_duplicate_group": False,
        "duplicate_group": None,
        "fields": fields,
    }


def record(index: int, status: str, candidates: list[dict[str, object]]) -> dict[str, object]:
    return {
        "source_file": "sample.xlsx",
        "sheet": "PI",
        "行号": str(index),
        "result_json": "sample_gate2d.json",
        "parse_report_json": "sample_gate2d_parse_report.json",
        "query": {
            "product_category": "被套",
            "spec": "240*260cm",
            "color": "漂白色",
            "fabric": "贡缎/T300/C100",
            "composition": "C100",
            "style": "无飞边",
            "label_method": "客标",
            "size_type": "交货尺寸",
        },
        "retrieval": {
            "structured_candidates": 1,
            "vector_candidates": 2,
            "union_candidates": 2,
            "hard_conflict_removed": 0,
            "hard_conflicts_by_field": {},
            "post_filter_candidates": len(candidates),
        },
        "decision": {
            "status": status,
            "action": "manual_review",
            "top1_margin": 0.1,
            "comparable_field_count": 7,
            "reason": "fixture",
        },
        "candidates": candidates,
    }


def write_payloads(tmp_path: Path, records: list[dict[str, object]]) -> tuple[Path, Path, Path, Path]:
    output_root = tmp_path / "data" / "output"
    prototype = output_root / "material_match_prototype"
    prototype.mkdir(parents=True)
    candidates_path = prototype / "material_match_candidates.json"
    summary_path = prototype / "material_match_summary.json"
    decisions = Counter(row["decision"]["status"] for row in records)  # type: ignore[index]
    candidates_path.write_text(json.dumps({"records": records}, ensure_ascii=False), encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "summary": {
                    "order_records": len(records),
                    "records_with_candidates": sum(bool(row["candidates"]) for row in records),
                    "decision_statuses": dict(decisions),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    formal_dir = output_root / "gate2d_validation" / "all_results"
    formal_dir.mkdir(parents=True)
    formal_dir.joinpath("sample_gate2d.json").write_text(
        json.dumps(
            [{"行号": str(i), "客户": "Fixture", "物料名称": "Fixture 被套"} for i in range(1, len(records) + 1)],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = tmp_path / "material_master.sqlite3"
    write_store(store)
    return candidates_path, summary_path, store, tmp_path / "material_match_review.xlsx"


def test_materials_cli_build_and_validate_review(tmp_path) -> None:
    records = [record(1, "unique_best_candidate", [candidate("MAT-1")])]
    candidates_path, summary_path, store, workbook = write_payloads(tmp_path, records)

    build_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bedding_order_parser.materials",
            "build-review",
            "--candidates",
            str(candidates_path),
            "--summary",
            str(summary_path),
            "--store",
            str(store),
            "--output",
            str(workbook),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert build_result.returncode == 0
    assert "Review records: 1" in build_result.stdout

    wb = load_workbook(workbook)
    try:
        review = wb[REVIEW_SHEET]
        review["T2"] = "MAT-1"
        review["U2"] = "推荐编码正确"
        wb.save(workbook)
    finally:
        wb.close()

    validate_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bedding_order_parser.materials",
            "validate-review",
            "--workbook",
            str(workbook),
            "--store",
            str(store),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert validate_result.returncode == 0
    payload = json.loads(validate_result.stdout)
    assert payload["ok"] is True

    metrics_path = tmp_path / "review_metrics.json"
    evaluate_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bedding_order_parser.materials",
            "evaluate-review",
            "--workbook",
            str(workbook),
            "--store",
            str(store),
            "--output",
            str(metrics_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert evaluate_result.returncode == 0
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["counts"]["positive_truth_rows"] == 1
    assert metrics["ranking"]["top1_rate"] == 1.0
    assert "MAT-1" not in metrics_path.read_text(encoding="utf-8")


def test_build_review_requires_overwrite(tmp_path) -> None:
    records = [record(1, "unique_best_candidate", [candidate("MAT-1")])]
    candidates_path, summary_path, store, workbook = write_payloads(tmp_path, records)

    build_review_workbook(candidates_path, summary_path, store, workbook)
    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "bedding_order_parser.materials",
            "build-review",
            "--candidates",
            str(candidates_path),
            "--summary",
            str(summary_path),
            "--store",
            str(store),
            "--output",
            str(workbook),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert second.returncode == 1
    assert "already exists" in second.stderr
