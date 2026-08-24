"""Structured material candidate retrieval and candidate data contracts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from bedding_order_parser.exceptions import BeddingOrderParserError


class CandidateFilterError(BeddingOrderParserError):
    """Raised when structured material candidates cannot be loaded safely."""


@dataclass(frozen=True)
class OrderQuery:
    source_file: str
    sheet: str
    line_number: str
    result_json: str
    parse_report_json: str
    product_category: str
    spec: str
    color: str
    fabric: str
    fabric_category: str
    density: str
    composition: str
    style: str
    label_method: str
    size_type: str
    line_note: str
    embedding_text: str

    def to_dict(self) -> dict[str, str]:
        return {
            "product_category": self.product_category,
            "spec": self.spec,
            "color": self.color,
            "fabric": self.fabric,
            "fabric_category": self.fabric_category,
            "density": self.density,
            "composition": self.composition,
            "style": self.style,
            "label_method": self.label_method,
            "size_type": self.size_type,
            "line_note": self.line_note,
            "embedding_text": self.embedding_text,
        }


@dataclass(frozen=True)
class MaterialCandidate:
    material_code: str
    source_row: int
    product_category: str
    spec: str
    color: str
    fabric: str
    fabric_category: str
    density: str
    composition: str
    style: str
    label_method: str
    size_type: str
    embedding_text: str

    def comparable_values(self) -> dict[str, str]:
        return {
            "product_category": self.product_category,
            "spec": self.spec,
            "color": self.color,
            "fabric": self.fabric,
            "fabric_category": self.fabric_category,
            "density": self.density,
            "composition": self.composition,
            "style": self.style,
            "label_method": self.label_method,
            "size_type": self.size_type,
        }


_CANDIDATE_COLUMNS = """
    material_code,
    source_row,
    product_category,
    spec_normalized,
    color_normalized,
    fabric_normalized,
    fabric_category_normalized,
    density_normalized,
    composition_normalized,
    style_normalized,
    label_method_normalized,
    size_type_normalized,
    embedding_text
"""


def load_all_material_candidates(
    store_path: str | Path,
) -> dict[str, MaterialCandidate]:
    """Load every material keyed by its original string code."""
    path = Path(store_path).expanduser().resolve()
    if not path.is_file():
        raise CandidateFilterError(f"Material SQLite store does not exist: {path}")
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                f"SELECT {_CANDIDATE_COLUMNS} FROM materials"
            ).fetchall()
    except sqlite3.Error as exc:
        raise CandidateFilterError(f"Unable to load material candidates: {exc}") from exc

    candidates: dict[str, MaterialCandidate] = {}
    for row in rows:
        candidate = _candidate_from_row(row)
        if not candidate.material_code:
            raise CandidateFilterError("Material candidate has an empty code.")
        if candidate.material_code in candidates:
            raise CandidateFilterError(
                f"Duplicate material candidate code: {candidate.material_code}"
            )
        candidates[candidate.material_code] = candidate
    return candidates


def retrieve_structured_candidate_codes(
    store_path: str | Path,
    query: OrderQuery,
) -> list[str]:
    """Recall candidates through comparable SQLite columns.

    Missing query fields add no SQL condition. Missing candidate fields remain
    eligible and are explained later by the field comparator.
    """
    path = Path(store_path).expanduser().resolve()
    if not path.is_file():
        raise CandidateFilterError(f"Material SQLite store does not exist: {path}")

    conditions: list[str] = []
    parameters: list[str] = []
    if query.product_category:
        conditions.append("product_category = ?")
        parameters.append(query.product_category)
    for column, value in (
        ("color_normalized", query.color),
        ("density_normalized", query.density),
        ("composition_normalized", query.composition),
        ("size_type_normalized", query.size_type),
    ):
        if not value:
            continue
        conditions.append(f"({column} = ? OR {column} = '')")
        parameters.append(value)

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT material_code FROM materials{where_clause}"
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(sql, parameters).fetchall()
    except sqlite3.Error as exc:
        raise CandidateFilterError(
            f"Unable to retrieve structured material candidates: {exc}"
        ) from exc
    return [str(row[0]) for row in rows]


def merge_candidate_codes(
    structured_codes: Iterable[str],
    vector_codes: Iterable[str],
) -> list[str]:
    """Return a stable union without treating source order as business rank."""
    seen: set[str] = set()
    merged: list[str] = []
    for code in (*tuple(structured_codes), *tuple(vector_codes)):
        if code and code not in seen:
            seen.add(code)
            merged.append(code)
    return merged


def _candidate_from_row(row: tuple[Any, ...]) -> MaterialCandidate:
    return MaterialCandidate(
        material_code=str(row[0]),
        source_row=int(row[1]),
        product_category=str(row[2] or ""),
        spec=str(row[3] or ""),
        color=str(row[4] or ""),
        fabric=str(row[5] or ""),
        fabric_category=str(row[6] or ""),
        density=str(row[7] or ""),
        composition=str(row[8] or ""),
        style=str(row[9] or ""),
        label_method=str(row[10] or ""),
        size_type=str(row[11] or ""),
        embedding_text=str(row[12] or ""),
    )
