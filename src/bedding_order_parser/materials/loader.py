"""Read and audit material_info.csv without mutating it."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.materials.models import (
    EXPECTED_HEADERS,
    RAW_FIELD_NAMES,
    RawMaterialRow,
    SourceAudit,
)


class MaterialLoadError(BeddingOrderParserError):
    """Raised when material master CSV cannot be safely loaded."""


def compute_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_material_csv(path: str | Path) -> tuple[list[RawMaterialRow], SourceAudit]:
    display_path = Path(path)
    resolved = display_path.expanduser().resolve()
    if not resolved.exists():
        raise MaterialLoadError(f"Material source does not exist: {resolved}")
    raw_bytes = resolved.read_bytes()
    encoding, text = _decode(raw_bytes)
    delimiter = _detect_delimiter(text)
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    if not rows:
        raise MaterialLoadError(f"Material source is empty: {resolved}")

    headers = rows[0]
    if tuple(headers) != EXPECTED_HEADERS:
        raise MaterialLoadError(
            "Material CSV headers do not match expected contract: "
            f"expected {list(EXPECTED_HEADERS)}, got {headers}"
        )

    material_rows: list[RawMaterialRow] = []
    invalid_rows = 0
    row_signatures: list[tuple[str, ...]] = []
    empty_counts = {header: 0 for header in EXPECTED_HEADERS}
    unique_values = {header: set() for header in EXPECTED_HEADERS}

    for source_row, row in enumerate(rows[1:], start=2):
        if len(row) != len(EXPECTED_HEADERS):
            invalid_rows += 1
            continue
        values = {header: _cell(row[index]) for index, header in enumerate(EXPECTED_HEADERS)}
        for header, value in values.items():
            if value == "":
                empty_counts[header] += 1
            unique_values[header].add(value)
        material_code = values["物料编码"]
        raw = {field: values[field] for field in RAW_FIELD_NAMES}
        material_rows.append(
            RawMaterialRow(
                source_row=source_row,
                material_code=material_code,
                raw=raw,
            )
        )
        row_signatures.append(tuple(values[header] for header in EXPECTED_HEADERS))

    codes = [row.material_code for row in material_rows]
    code_counts = Counter(codes)
    empty_material_code = code_counts.get("", 0)
    duplicate_material_code = sum(
        count - 1 for code, count in code_counts.items() if code and count > 1
    )
    exact_duplicate_rows = sum(
        count - 1 for count in Counter(row_signatures).values() if count > 1
    )

    audit = SourceAudit(
        path=display_path,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        size=resolved.stat().st_size,
        encoding=encoding,
        delimiter=delimiter,
        headers=headers,
        row_count=len(material_rows),
        empty_material_code=empty_material_code,
        duplicate_material_code=duplicate_material_code,
        exact_duplicate_rows=exact_duplicate_rows,
        invalid_rows=invalid_rows,
        empty_counts=empty_counts,
        unique_counts={header: len(values) for header, values in unique_values.items()},
    )
    if invalid_rows:
        raise MaterialLoadError(f"Material CSV contains invalid row widths: {invalid_rows}")
    if empty_material_code:
        raise MaterialLoadError(f"Material CSV contains empty material codes: {empty_material_code}")
    if duplicate_material_code:
        raise MaterialLoadError(
            f"Material CSV contains duplicate material codes: {duplicate_material_code}"
        )
    return material_rows, audit


def _decode(raw_bytes: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return encoding, raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise MaterialLoadError("Material CSV encoding is not supported.")


def _detect_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
