"""Deterministic material master normalization."""

from __future__ import annotations

import re
import unicodedata

from bedding_order_parser.materials.models import NORMALIZED_FIELD_MAP, MaterialRecord, RawMaterialRow


def normalize_material(row: RawMaterialRow) -> MaterialRecord:
    normalized = {
        "product_category": normalize_product_category(row.raw["物料名称"]),
        "spec": normalize_spec(row.raw["规格"]),
        "color": normalize_color(row.raw["颜色"]),
        "fabric": normalize_text(row.raw["面料"]),
        "style": normalize_text(row.raw["款式"]),
        "label_method": normalize_text(row.raw["加标方式"]),
        "size_type": normalize_text(row.raw["尺寸类型"]),
        "fabric_category": normalize_text(row.raw["面料-品类"]),
        "yarn_count": normalize_yarn_count(row.raw["面料-纱支"]),
        "density": normalize_density(row.raw["面料-密度"]),
        "composition": normalize_composition(row.raw["面料-涤棉成分"]),
    }
    return MaterialRecord(
        source_row=row.source_row,
        material_code=row.material_code,
        raw={field: str(row.raw.get(field, "")) for field in NORMALIZED_FIELD_MAP},
        normalized=normalized,
        embedding_text="",
    )


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()


def audit_text(value: object) -> str:
    return normalize_text(value).casefold()


def normalize_product_category(material_name: str) -> str:
    text = audit_text(material_name)
    if re.search(r"被套|被罩|duvet\s*cover|dubet\s*cover|quilt\s*cover", text):
        return "被套"
    return ""


def normalize_spec(value: str) -> str:
    text = audit_text(value).replace("×", "*").replace("x", "*")
    text = re.sub(r"\s+", "", text)
    match = re.search(
        r"(?P<a>\d+(?:\.\d+)?)(?P<unit1>cm|mm|inch|in|\")?\*"
        r"(?P<b>\d+(?:\.\d+)?)(?P<unit2>cm|mm|inch|in|\")?",
        text,
    )
    if not match:
        return normalize_text(value).replace("×", "*").replace("X", "*").replace("x", "*")
    unit = _unit(match.group("unit1") or match.group("unit2"))
    first = _to_cm(float(match.group("a")), unit)
    second = _to_cm(float(match.group("b")), unit)
    suffix = _structural_extension(text)
    return f"{_number(first)}*{_number(second)}cm{suffix}"


def normalize_color(value: str) -> str:
    raw = normalize_text(value)
    text = raw.casefold()
    if raw in {"漂白色", "本白", "本白色", "浅灰色", "深灰色", "灰色", "蓝色", "米色"}:
        return "漂白色" if raw in {"本白", "本白色"} else raw
    if re.search(r"\blight\s+gr[ae]y\b|浅灰", text):
        return "浅灰色"
    if re.search(r"\bdark\s+gr[ae]y\b|深灰", text):
        return "深灰色"
    if re.search(r"\bplain\s+white\b|\bwhite\b|漂白", text):
        return "漂白色"
    if re.search(r"\bgr[ae]y\b|灰", text):
        return "灰色"
    if re.search(r"\bbeige\b|米", text):
        return "米色"
    if re.search(r"\bblue\b|蓝", text):
        return "蓝色"
    return raw


def normalize_yarn_count(value: str) -> str:
    text = normalize_text(value).upper().replace("×", "*").replace("X", "*")
    return re.sub(r"\s+", "", text)


def normalize_density(value: str) -> str:
    text = normalize_text(value).upper().replace("×", "*").replace("X", "*")
    match = re.search(r"(?:T|TC)?\s*(\d{2,4})", text)
    if match and "*" not in text:
        return f"T{int(match.group(1))}"
    return re.sub(r"\s+", "", text)


def normalize_composition(value: str) -> str:
    text = normalize_text(value).upper().replace(" ", "")
    if text in {"C100", "100C", "100%C", "100%棉"}:
        return "C100"
    match = re.search(r"C(\d{1,3})/?T(\d{1,3})", text)
    if match:
        return f"C{int(match.group(1))}/T{int(match.group(2))}"
    match = re.search(r"T(\d{1,3})/?C(\d{1,3})", text)
    if match:
        return f"C{int(match.group(2))}/T{int(match.group(1))}"
    return text


def _unit(unit: str | None) -> str:
    normalized = (unit or "cm").casefold()
    if normalized in {'"', "in"}:
        return "inch"
    return normalized


def _to_cm(value: float, unit: str) -> float:
    if unit == "mm":
        return value / 10
    if unit == "inch":
        return value * 2.54
    return value


def _structural_extension(text: str) -> str:
    match = re.search(r"\+\s*(\d+(?:\.\d+)?)(mm|cm|inch|in|\")?", text)
    if not match:
        return ""
    return f"+{_number(_to_cm(float(match.group(1)), _unit(match.group(2))))}cm"


def _number(value: float) -> str:
    rounded = round(value, 2)
    nearest_integer = round(rounded)
    if abs(rounded - nearest_integer) < 0.02:
        return str(int(nearest_integer))
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")