"""Build the canonical SQLite and JSONL material store."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import time
from collections import Counter
from pathlib import Path
from tempfile import mkdtemp

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.materials.document_builder import attach_embedding_text
from bedding_order_parser.materials.loader import compute_sha256, load_material_csv
from bedding_order_parser.materials.models import BuildResult, MaterialRecord, SourceAudit
from bedding_order_parser.materials.normalizer import audit_text, normalize_material


class MaterialStoreError(BeddingOrderParserError):
    """Raised when material store outputs cannot be safely built."""


def build_material_store(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> BuildResult:
    started = time.perf_counter()
    source = Path(source_path).expanduser().resolve()
    target = Path(output_dir).expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise MaterialStoreError(
            f"Material store output already exists; pass --overwrite: {target}"
        )

    source_sha_before = compute_sha256(source)
    rows, audit = load_material_csv(source_path)
    records = [attach_embedding_text(normalize_material(row)) for row in rows]
    manifest = build_manifest(audit, records)

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(mkdtemp(prefix=f".{target.name}.", dir=parent))
    try:
        sqlite_path = temp_dir / "material_master.sqlite3"
        jsonl_path = temp_dir / "material_documents.jsonl"
        manifest_path = temp_dir / "material_store_manifest.json"
        sqlite_records = _write_sqlite(sqlite_path, records)
        jsonl_records = _write_jsonl(jsonl_path, records)
        manifest["outputs"]["sqlite_records"] = sqlite_records
        manifest["outputs"]["jsonl_records"] = jsonl_records
        _write_json(manifest_path, manifest)

        source_sha_after = compute_sha256(source)
        if source_sha_after != source_sha_before or source_sha_after != audit.sha256:
            raise MaterialStoreError("Source CSV SHA-256 changed during material store build.")

        if target.exists():
            if not overwrite and any(target.iterdir()):
                raise MaterialStoreError(
                    f"Material store output already exists; pass --overwrite: {target}"
                )
            if overwrite:
                shutil.rmtree(target)
            else:
                target.rmdir()
        temp_dir.rename(target)
        output_sizes = {
            "sqlite": (target / "material_master.sqlite3").stat().st_size,
            "jsonl": (target / "material_documents.jsonl").stat().st_size,
            "manifest": (target / "material_store_manifest.json").stat().st_size,
        }
        return BuildResult(
            source_audit=audit,
            source_sha256_after=source_sha_after,
            output_dir=target,
            sqlite_path=target / "material_master.sqlite3",
            jsonl_path=target / "material_documents.jsonl",
            manifest_path=target / "material_store_manifest.json",
            sqlite_records=sqlite_records,
            jsonl_records=jsonl_records,
            elapsed_seconds=time.perf_counter() - started,
            output_sizes=output_sizes,
            manifest=manifest,
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def build_manifest(audit: SourceAudit, records: list[MaterialRecord]) -> dict:
    category_counts = _category_counts(records)
    return {
        "source": {
            "path": _relative_or_absolute(audit.path),
            "sha256": audit.sha256,
            "size": audit.size,
            "encoding": audit.encoding,
            "delimiter": audit.delimiter,
            "row_count": audit.row_count,
            "headers": audit.headers,
        },
        "quality": {
            "empty_material_code": audit.empty_material_code,
            "duplicate_material_code": audit.duplicate_material_code,
            "exact_duplicate_rows": audit.exact_duplicate_rows,
            "invalid_rows": audit.invalid_rows,
            "empty_counts": audit.empty_counts,
            "unique_counts": audit.unique_counts,
        },
        "category": category_counts,
        "statistics": _statistics(records),
        "outputs": {
            "sqlite_records": 0,
            "jsonl_records": 0,
        },
    }


def _write_sqlite(path: Path, records: list[MaterialRecord]) -> int:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE materials (
                material_code TEXT PRIMARY KEY,
                source_row INTEGER NOT NULL,
                material_name_raw TEXT NOT NULL,
                product_category TEXT NOT NULL,
                spec_raw TEXT NOT NULL,
                spec_normalized TEXT NOT NULL,
                color_raw TEXT NOT NULL,
                color_normalized TEXT NOT NULL,
                fabric_raw TEXT NOT NULL,
                fabric_normalized TEXT NOT NULL,
                style_raw TEXT NOT NULL,
                style_normalized TEXT NOT NULL,
                label_method_raw TEXT NOT NULL,
                label_method_normalized TEXT NOT NULL,
                size_type_raw TEXT NOT NULL,
                size_type_normalized TEXT NOT NULL,
                fabric_category_raw TEXT NOT NULL,
                fabric_category_normalized TEXT NOT NULL,
                yarn_count_raw TEXT NOT NULL,
                yarn_count_normalized TEXT NOT NULL,
                density_raw TEXT NOT NULL,
                density_normalized TEXT NOT NULL,
                composition_raw TEXT NOT NULL,
                composition_normalized TEXT NOT NULL,
                embedding_text TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO materials VALUES (
                :material_code, :source_row, :material_name_raw, :product_category,
                :spec_raw, :spec_normalized, :color_raw, :color_normalized,
                :fabric_raw, :fabric_normalized, :style_raw, :style_normalized,
                :label_method_raw, :label_method_normalized,
                :size_type_raw, :size_type_normalized,
                :fabric_category_raw, :fabric_category_normalized,
                :yarn_count_raw, :yarn_count_normalized,
                :density_raw, :density_normalized,
                :composition_raw, :composition_normalized, :embedding_text
            )
            """,
            [_sqlite_row(record) for record in records],
        )
        for column in (
            "product_category",
            "spec_normalized",
            "color_normalized",
            "fabric_category_normalized",
            "density_normalized",
            "composition_normalized",
            "size_type_normalized",
        ):
            connection.execute(f"CREATE INDEX idx_materials_{column} ON materials ({column})")
        connection.commit()
        return connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    finally:
        connection.close()


def _write_jsonl(path: Path, records: list[MaterialRecord]) -> int:
    seen: set[str] = set()
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            if record.material_code in seen:
                raise MaterialStoreError(f"Duplicate JSONL document id: {record.material_code}")
            seen.add(record.material_code)
            handle.write(json.dumps(record.to_document_dict(), ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sqlite_row(record: MaterialRecord) -> dict[str, object]:
    return {
        "material_code": record.material_code,
        "source_row": record.source_row,
        "material_name_raw": record.raw["物料名称"],
        "product_category": record.normalized["product_category"],
        "spec_raw": record.raw["规格"],
        "spec_normalized": record.normalized["spec"],
        "color_raw": record.raw["颜色"],
        "color_normalized": record.normalized["color"],
        "fabric_raw": record.raw["面料"],
        "fabric_normalized": record.normalized["fabric"],
        "style_raw": record.raw["款式"],
        "style_normalized": record.normalized["style"],
        "label_method_raw": record.raw["加标方式"],
        "label_method_normalized": record.normalized["label_method"],
        "size_type_raw": record.raw["尺寸类型"],
        "size_type_normalized": record.normalized["size_type"],
        "fabric_category_raw": record.raw["面料-品类"],
        "fabric_category_normalized": record.normalized["fabric_category"],
        "yarn_count_raw": record.raw["面料-纱支"],
        "yarn_count_normalized": record.normalized["yarn_count"],
        "density_raw": record.raw["面料-密度"],
        "density_normalized": record.normalized["density"],
        "composition_raw": record.raw["面料-涤棉成分"],
        "composition_normalized": record.normalized["composition"],
        "embedding_text": record.embedding_text,
    }


def _category_counts(records: list[MaterialRecord]) -> dict[str, object]:
    other_types = Counter()
    unrecognized = 0
    duvet = 0
    for record in records:
        if record.normalized["product_category"] == "被套":
            duvet += 1
            continue
        other = _other_product_type(record.raw["物料名称"])
        if other:
            other_types[other] += 1
        else:
            unrecognized += 1
    return {
        "duvet_cover_records": duvet,
        "other_records": sum(other_types.values()),
        "unrecognized_records": unrecognized,
        "other_type_top20": dict(other_types.most_common(20)),
    }


def _statistics(records: list[MaterialRecord]) -> dict[str, object]:
    return {
        "spec_format_distribution": dict(Counter(_spec_format(record.normalized["spec"]) for record in records)),
        "color_top20": dict(Counter(record.normalized["color"] for record in records if record.normalized["color"]).most_common(20)),
        "fabric_category_top20": dict(Counter(record.normalized["fabric_category"] for record in records if record.normalized["fabric_category"]).most_common(20)),
        "density_distribution": dict(Counter(record.normalized["density"] for record in records if record.normalized["density"]).most_common()),
        "composition_distribution": dict(Counter(record.normalized["composition"] for record in records if record.normalized["composition"]).most_common()),
        "empty_style_count": sum(1 for record in records if not record.normalized["style"]),
        "unrecognized_product_category_rows": [
            record.source_row
            for record in records
            if not record.normalized["product_category"] and not _other_product_type(record.raw["物料名称"])
        ][:100],
    }


def _spec_format(spec: str) -> str:
    if not spec:
        return "empty"
    if "+" in spec:
        return "size_with_extension"
    if "*" in spec and spec.endswith("cm"):
        return "cm_size"
    return "other"


def _other_product_type(material_name: str) -> str:
    text = audit_text(material_name)
    patterns = (
        ("枕套", r"枕套|pillow\s*case|pillowcase"),
        ("床单", r"床单|bed\s*sheet|flat\s*sheet|fitted\s*sheet"),
        ("床笠", r"床笠|fitted"),
        ("保护垫", r"保护垫|mattress\s*protector|pad"),
        ("床裙", r"床裙|bed\s*skirt"),
        ("毛巾", r"毛巾|towel"),
        ("浴袍", r"浴袍|robe"),
        ("芯类", r"枕芯|被芯|duvet\s*insert|pillow"),
    )
    for label, pattern in patterns:
        if re.search(pattern, text):
            return label
    return ""


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)

