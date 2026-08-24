"""Models for canonical material master rows and store build results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXPECTED_HEADERS: tuple[str, ...] = (
    "物料编码",
    "物料名称",
    "规格",
    "颜色",
    "面料",
    "款式",
    "加标方式",
    "尺寸类型",
    "面料-品类",
    "面料-纱支",
    "面料-密度",
    "面料-涤棉成分",
)

RAW_FIELD_NAMES: tuple[str, ...] = EXPECTED_HEADERS[1:]

NORMALIZED_FIELD_MAP: dict[str, str] = {
    "物料名称": "product_category",
    "规格": "spec",
    "颜色": "color",
    "面料": "fabric",
    "款式": "style",
    "加标方式": "label_method",
    "尺寸类型": "size_type",
    "面料-品类": "fabric_category",
    "面料-纱支": "yarn_count",
    "面料-密度": "density",
    "面料-涤棉成分": "composition",
}


@dataclass(frozen=True)
class RawMaterialRow:
    source_row: int
    material_code: str
    raw: dict[str, str]


@dataclass(frozen=True)
class MaterialRecord:
    source_row: int
    material_code: str
    raw: dict[str, str]
    normalized: dict[str, str]
    embedding_text: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "source_row": self.source_row,
            "material_code": self.material_code,
            "raw": self.raw,
            "normalized": self.normalized,
            "embedding_text": self.embedding_text,
        }

    def to_document_dict(self) -> dict[str, Any]:
        return {
            "id": self.material_code,
            "text": self.embedding_text,
            "metadata": {
                "source_row": self.source_row,
                "product_category": self.normalized["product_category"],
                "spec": self.normalized["spec"],
                "color": self.normalized["color"],
                "fabric_category": self.normalized["fabric_category"],
                "density": self.normalized["density"],
                "composition": self.normalized["composition"],
                "style": self.normalized["style"],
                "size_type": self.normalized["size_type"],
            },
        }


@dataclass(frozen=True)
class SourceAudit:
    path: Path
    sha256: str
    size: int
    encoding: str
    delimiter: str
    headers: list[str]
    row_count: int
    empty_material_code: int
    duplicate_material_code: int
    exact_duplicate_rows: int
    invalid_rows: int
    empty_counts: dict[str, int]
    unique_counts: dict[str, int]


@dataclass(frozen=True)
class BuildResult:
    source_audit: SourceAudit
    source_sha256_after: str
    output_dir: Path
    sqlite_path: Path
    jsonl_path: Path
    manifest_path: Path
    sqlite_records: int
    jsonl_records: int
    elapsed_seconds: float
    output_sizes: dict[str, int]
    manifest: dict[str, Any]
