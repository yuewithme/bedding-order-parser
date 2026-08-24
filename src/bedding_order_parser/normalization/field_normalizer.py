"""Deterministic baseline field normalization."""

from __future__ import annotations

import re


DEFAULT_PACKAGING = "纸箱（三瓦楞七层），内衬防水袋"
EMPTY_OPTIONAL_TEXTS = {"", "/", "-", "--", "－", "n/a", "na", "none", "null"}


def normalize_quantity(value: str) -> str:
    text = clean_text(value)
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def normalize_component(text: str) -> str:
    lowered = _compact_percent_text(text)
    if re.search(
        r"100\s*%\s*cott?on|100\s*%\s*ring\s*spun\s*cott?on|100\s*%c|100%c",
        lowered,
    ):
        return "100C"

    match = re.search(
        r"(\d{1,3})\s*%\s*cotton\s*[/, ]+\s*(\d{1,3})\s*%\s*poly(?:ester)?",
        lowered,
    )
    if not match:
        match = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})\s*cotton\s*/\s*poly", lowered)
    if match:
        cotton, polyester = match.groups()
        return f"C{int(cotton)}/T{int(polyester)}"

    compact = lowered.replace(" ", "")
    if "80/20cotton/poly" in compact or "c80/t20" in compact:
        return "C80/T20"
    if "50/50cotton/poly" in compact or "c50/t50" in compact:
        return "C50/T50"
    return ""


def normalize_color(text: str) -> str:
    lowered = text.casefold()
    if "light grey" in lowered or "light gray" in lowered:
        return "浅灰色"
    if "grey" in lowered or "gray" in lowered:
        return "灰色"
    if "white" in lowered or "plain white" in lowered:
        return "漂白色"
    return "漂白色"


def normalize_size_type(text: str) -> str:
    compact = re.sub(r"\s+", "", text.casefold())
    lowered = text.casefold()
    if "before wash" in lowered or "delivery size" in lowered:
        return "交货尺寸"
    if "after wash" in lowered or "afterwash" in compact or "after washing" in lowered:
        return "洗涤尺寸"
    return "洗涤尺寸"


def normalize_yes_no_embroidery(text: str) -> str:
    lowered = text.casefold()
    if re.search(r"\b(?:no|without)\s+embroider(?:y|ed|ing)\b", lowered):
        return "N"
    if "embroidery" in lowered or "embroidered" in lowered:
        return "Y"
    return "N"


def normalize_labeling(text: str) -> str:
    return "客标"


def normalize_optional_text(value: str) -> str:
    cleaned = clean_text(value)
    if cleaned.casefold() in EMPTY_OPTIONAL_TEXTS:
        return ""
    return cleaned


def normalize_size(size_text: str, specification_text: str = "") -> str:
    cleaned_size = clean_text(size_text)
    dimensions = _extract_labeled_dimensions(cleaned_size)
    default_unit = _detect_default_unit(cleaned_size)
    if "W" in dimensions and "L" in dimensions:
        width = _to_cm(*dimensions["W"], default_unit)
        length = _to_cm(*dimensions["L"], default_unit)
    else:
        numbers = _extract_number_unit_pairs(cleaned_size)
        if len(numbers) < 2:
            return cleaned_size
        width = _to_cm(*numbers[0], default_unit)
        length = _to_cm(*numbers[1], default_unit)

    suffix = _extract_extra_size(specification_text, default_unit)
    return f"{_format_number(length)}*{_format_number(width)}{suffix}cm"


def normalize_fabric(text: str) -> str:
    parts: list[str] = []
    category = _fabric_category(text)
    thread_count = _thread_count(text)
    component = normalize_component(text)
    if category:
        parts.append(category)
    if thread_count:
        parts.append(thread_count)
    if component:
        parts.append(component)
    return "/".join(parts)


def normalize_style(text: str) -> str:
    lowered = clean_text(text).casefold()
    has_bag = bool(re.search(r"\bbag\b|\bbag style\b|\bbag model\b|\bopen bag\b", lowered))
    has_envelope = "envelope" in lowered or ("flap" in lowered and not has_bag)
    has_hand_hole = _has_positive_hand_hole(lowered)
    has_no_flange = bool(re.search(r"\bno\s+(?:flange|falnge)\b|\bwithout\s+(?:flange|falnge)\b", lowered))
    has_flange = bool(re.search(r"\b(?:flange|falnge)\b", lowered)) and not has_no_flange
    has_three_side_flange = bool(
        re.search(r"\b(?:3|three)\s*sides?\s+flange\b|\bflange\s+for\s+(?:3|three)\s+sides?\b", lowered)
    )
    has_tail_flange = bool(re.search(r"\b5\s*cm\s*(?:flange|hem)\b|\binternal\s+fold\b", lowered))
    has_no_tie = bool(re.search(r"\bno\s+ties?\b|\bwithout\s+ties?\b", lowered))
    has_tie = bool(re.search(r"\bties?\b", lowered)) and not has_no_tie
    has_zip = "zipper" in lowered or re.search(r"\bzip\b", lowered) is not None
    closure_text = "有拉链" if has_zip else ("有系带" if has_tie else "无系带")
    welcome_text = "迎宾" if has_hand_hole else ""

    if has_bag:
        if has_three_side_flange:
            return f"三飞边双层口叠边口袋{closure_text}{welcome_text}式"
        if has_tail_flange or (has_flange and has_hand_hole):
            return f"被尾单飞边双层口叠边口袋{closure_text}{welcome_text}式"
        flange_text = "飞边" if has_flange else "无飞边"
        return f"{flange_text}口袋{closure_text}{welcome_text}式"

    if has_envelope:
        return "无飞边平口信封迎宾式" if has_hand_hole else "无飞边平口信封式"
    return ""


def _has_positive_hand_hole(lowered: str) -> bool:
    hand_pattern = r"\bhands?\s+holes?\b|\bhand\s+holes?\b|\bhand\s+holds?\b"
    if re.search(hand_pattern, lowered) is None:
        return False
    negative_pattern = r"\b(?:no|without)\s+hands?\s+holes?\b|\b(?:no|without)\s+hand\s+holes?\b|\b(?:no|without)\s+hand\s+holds?\b"
    return re.search(negative_pattern, lowered) is None


def normalize_row_note(text: str) -> str:
    notes: list[str] = []
    extra = _extract_extra_size(text)
    if extra:
        notes.append(f"重叠片{extra.removeprefix('+')}")
    if re.search(r"\bhands?\s+holes?\b|\bhand\s+holds?\b", text.casefold()):
        notes.append("含手洞")
    if normalize_yes_no_embroidery(text) == "Y":
        notes.append("有绣花")
    return "，".join(notes)


def clean_text(text: str) -> str:
    return re.sub(r"\s{2,}", " ", str(text).replace("\r\n", " ").replace("\n", " ")).strip()


def _compact_percent_text(text: str) -> str:
    return clean_text(text).casefold().replace("％", "%")


def _extract_labeled_dimensions(text: str) -> dict[str, tuple[str, str]]:
    dimensions: dict[str, tuple[str, str]] = {}
    unit_pattern = r"(mm|cm|inches|inch|in|\")?"
    suffix_pattern = re.compile(
        rf"(\d+(?:\.\d+)?)\s*(?:{unit_pattern})\s*(w|width|l|length)\b\s*(?:{unit_pattern})",
        flags=re.IGNORECASE,
    )
    prefix_pattern = re.compile(
        rf"\b(w|width|l|length)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:{unit_pattern})",
        flags=re.IGNORECASE,
    )
    for match in suffix_pattern.finditer(text):
        value, unit_before, label, unit_after = match.groups()
        key = "W" if label.casefold().startswith("w") else "L"
        dimensions[key] = (value, _normalize_unit(unit_before or unit_after))
    for match in prefix_pattern.finditer(text):
        label, value, unit = match.groups()
        key = "W" if label.casefold().startswith("w") else "L"
        dimensions[key] = (value, _normalize_unit(unit))
    return dimensions


def _extract_number_unit_pairs(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|inches|inch|in|\")?", flags=re.IGNORECASE)
    return [(value, _normalize_unit(unit)) for value, unit in pattern.findall(text)]


def _detect_default_unit(text: str) -> str:
    lowered = text.casefold()
    if "mm" in lowered:
        return "mm"
    if "cm" in lowered:
        return "cm"
    if re.search(r"\d+(?:\.\d+)?\s*(?:inches|inch|in|\")", lowered):
        return "in"
    return "cm"


def _normalize_unit(unit: str | None) -> str:
    if not unit:
        return ""
    unit = unit.casefold()
    if unit in {"inch", "inches", '"'}:
        return "in"
    return unit


def _to_cm(value: str, unit: str, default_unit: str) -> float:
    number = float(value)
    effective_unit = unit or default_unit
    if effective_unit == "mm":
        return number / 10
    if effective_unit == "in":
        return number * 2.54
    return number


def _format_number(value: str | float) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(number).rstrip("0").rstrip(".")


def _extract_extra_size(text: str, default_unit: str = "cm") -> str:
    lowered = clean_text(text).casefold()
    unit_pattern = r"(mm|cm|inches|inch|in|\")"
    target_pattern = r"(?:inner\s+flap|envelope\s+flap|flap|overlap(?:ping)?|tongue|重叠片|内舌)"
    patterns = (
        rf"(?:{target_pattern})\s*(?:[:：=]|with|of|is)?\s*(\d+(?:\.\d+)?)\s*{unit_pattern}",
        rf"(\d+(?:\.\d+)?)\s*{unit_pattern}\s*(?:{target_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            value = match.group(1)
            unit = _normalize_unit(match.group(2) or "")
            return f"+{_format_number(_to_cm(value, unit, default_unit))}"
    return ""

def _thread_count(text: str) -> str:
    match = re.search(r"\bT\s*(\d{3})\b", text, flags=re.IGNORECASE)
    if match:
        return f"T{match.group(1)}"
    match = re.search(r"(\d{3})\s*TC\b", text, flags=re.IGNORECASE)
    if match:
        return f"T{match.group(1)}"
    match = re.search(r"\b(\d{3})\s*thread\s*count\b", text, flags=re.IGNORECASE)
    if match:
        return f"T{match.group(1)}"
    return ""


def _fabric_category(text: str) -> str:
    lowered = text.casefold()
    if "stripe" in lowered or "stripes" in lowered or "缎条" in text:
        return "缎条"
    if "twill" in lowered:
        return "斜纹"
    if "plain woven" in lowered or "plain weave" in lowered:
        return "平布"
    if "sateen" in lowered or "satin" in lowered or "percale" in lowered:
        return "贡缎"
    return ""
