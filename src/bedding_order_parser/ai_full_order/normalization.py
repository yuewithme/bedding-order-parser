"""Conservative, versioned local normalization for AI-first field decisions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum


NORMALIZATION_VERSION = "1.0"

_WHITESPACE_RE = re.compile(r"\s+")
_QUANTITY_RE = re.compile(r"\d+(?:\.\d+)?")
_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_SLASH_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
_CHINESE_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

_CURRENCY_ALIASES = {
    "usd": "USD",
    "us dollar": "USD",
    "美元": "USD",
}
_FORMALLY_NORMALIZED_FIELDS = frozenset({"币种", "数量", "计划发货日期"})


class NormalizationStatus(StrEnum):
    UNCHANGED = "unchanged"
    NORMALIZED = "normalized"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class BusinessValueView:
    """The source display value and any deterministic local normalization."""

    display_value: str
    normalized_value: str
    normalization_status: NormalizationStatus
    normalization_rule: str = ""

    @property
    def formal_value(self) -> str:
        """Use a normalized representation only where downstream has a fixed format."""
        return self.normalized_value


def build_business_value_view(field_name: str, value: str) -> BusinessValueView:
    """Return only deterministic, non-semantic normalizations for one business value."""
    display_value = str(value)
    if not display_value:
        return BusinessValueView(
            display_value="",
            normalized_value="",
            normalization_status=NormalizationStatus.NOT_APPLICABLE,
        )

    text = _normalize_text(display_value)
    normalized = text
    rule = "unicode_whitespace" if text != display_value else ""

    if field_name == "币种":
        mapped = _CURRENCY_ALIASES.get(text.casefold())
        if mapped:
            normalized, rule = mapped, "currency_alias"
    elif field_name == "数量":
        quantity = _normalize_quantity(text)
        if quantity is not None:
            normalized, rule = quantity, "decimal_quantity"
    elif field_name == "计划发货日期":
        normalized_date = _normalize_date(text)
        if normalized_date is not None:
            normalized, rule = normalized_date, "calendar_date"

    return BusinessValueView(
        display_value=display_value,
        normalized_value=normalized,
        normalization_status=(
            NormalizationStatus.NORMALIZED
            if normalized != display_value
            else NormalizationStatus.UNCHANGED
        ),
        normalization_rule=rule,
    )


def formal_value_for_field(field_name: str, view: BusinessValueView) -> str:
    """Keep AI wording except for the three fields with an explicit formal format."""
    if field_name in _FORMALLY_NORMALIZED_FIELDS:
        return view.formal_value
    return view.display_value


def note_layout_equivalent(left: str, right: str) -> bool:
    """Allow deterministic note layout cleanup without accepting semantic expansion."""
    return _normalize_note_layout(left) == _normalize_note_layout(right)


def _normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _normalize_note_layout(value: str) -> str:
    text = _normalize_text(value)
    text = re.sub(r"\s*([,;:!?.，；：！？。])\s*", r"\1", text)
    return re.sub(r"[,;:!?.，；：！？。]+", "", text)


def _normalize_quantity(value: str) -> str | None:
    if _QUANTITY_RE.fullmatch(value) is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    normalized = format(parsed.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _normalize_date(value: str) -> str | None:
    for pattern in (_ISO_DATE_RE, _SLASH_DATE_RE, _CHINESE_DATE_RE):
        match = pattern.fullmatch(value)
        if match is None:
            continue
        try:
            return date(*(int(part) for part in match.groups())).isoformat()
        except ValueError:
            return None
    return None
