from __future__ import annotations

import sqlite3
from pathlib import Path

from bedding_order_parser.materials.candidate_filter import (
    OrderQuery,
    merge_candidate_codes,
    retrieve_structured_candidate_codes,
)


def query(**overrides: str) -> OrderQuery:
    values = {
        "source_file": "sample.xlsx",
        "sheet": "PI",
        "line_number": "1",
        "result_json": "sample_gate2d.json",
        "parse_report_json": "sample_gate2d_parse_report.json",
        "product_category": "",
        "spec": "",
        "color": "",
        "fabric": "",
        "fabric_category": "",
        "density": "",
        "composition": "",
        "style": "",
        "label_method": "",
        "size_type": "",
        "line_note": "",
        "embedding_text": "sample",
    }
    values.update(overrides)
    return OrderQuery(**values)


def write_store(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE materials (
                material_code TEXT PRIMARY KEY,
                product_category TEXT NOT NULL,
                color_normalized TEXT NOT NULL,
                density_normalized TEXT NOT NULL,
                composition_normalized TEXT NOT NULL,
                size_type_normalized TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO materials VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("A", "被套", "漂白色", "T300", "C100", "交货尺寸"),
                ("B", "被套", "", "", "", ""),
                ("C", "被套", "灰色", "T400", "C80/T20", "洗涤尺寸"),
            ],
        )


def test_two_recall_sources_are_merged_as_union() -> None:
    assert merge_candidate_codes(["A", "B"], ["B", "C"]) == ["A", "B", "C"]


def test_empty_query_fields_do_not_limit_structured_candidates(tmp_path) -> None:
    store = tmp_path / "materials.sqlite3"
    write_store(store)

    codes = retrieve_structured_candidate_codes(store, query())

    assert codes == ["A", "B", "C"]


def test_empty_candidate_fields_remain_eligible(tmp_path) -> None:
    store = tmp_path / "materials.sqlite3"
    write_store(store)

    codes = retrieve_structured_candidate_codes(
        store,
        query(
            product_category="被套",
            color="漂白色",
            density="T300",
            composition="C100",
            size_type="交货尺寸",
        ),
    )

    assert codes == ["A", "B"]
