"""Dataclasses for the read-only dictionary preview."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DictionarySource:
    file_name: str
    sha256: str
    sheet_name: str

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuleRow:
    source_row: int
    source_cells: dict[str, str]
    field_name: str
    rule_description: str
    standard_value: str
    notes: str
    raw_values: dict[str, str]
    default_rule: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FabricRow:
    source_row: int
    fabric_family: str
    fabric_standard: str
    color_standard: str
    composition_raw: str
    density: str
    raw_values: dict[str, str]

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StyleRow:
    source_row: int
    standard_name: str
    flange: str
    tie: str
    zipper: str
    has_pocket: str
    is_welcome_style: str
    other_structure: str
    dimensions: str
    raw_values: dict[str, str]

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DictionaryBundle:
    sources: list[DictionarySource]
    rules: list[RuleRow]
    fabrics: list[FabricRow]
    styles: list[StyleRow]
    summary: dict[str, int]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "sources": [source.to_json_dict() for source in self.sources],
            "summary": dict(self.summary),
            "rules": [row.to_json_dict() for row in self.rules],
            "fabrics": [row.to_json_dict() for row in self.fabrics],
            "styles": [row.to_json_dict() for row in self.styles],
        }
