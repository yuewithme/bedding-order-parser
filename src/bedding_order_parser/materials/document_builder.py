"""Build stable retrieval documents for material records."""

from __future__ import annotations

from dataclasses import replace

from bedding_order_parser.materials.models import MaterialRecord


EMBEDDING_FIELDS: tuple[tuple[str, str], ...] = (
    ("品类", "product_category"),
    ("规格", "spec"),
    ("颜色", "color"),
    ("面料", "fabric"),
    ("面料品类", "fabric_category"),
    ("纱支", "yarn_count"),
    ("密度", "density"),
    ("成分", "composition"),
    ("款式", "style"),
    ("加标方式", "label_method"),
    ("尺寸类型", "size_type"),
)


def attach_embedding_text(record: MaterialRecord) -> MaterialRecord:
    parts = [
        f"{label}:{record.normalized[key]}"
        for label, key in EMBEDDING_FIELDS
        if record.normalized.get(key)
    ]
    return replace(record, embedding_text="；".join(parts))
