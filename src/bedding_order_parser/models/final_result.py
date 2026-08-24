"""Final 20-field JSON result model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FINAL_FIELD_NAMES: tuple[str, ...] = (
    "客户",
    "币种",
    "业务员",
    "表头备注",
    "行号",
    "物料编码",
    "物料名称",
    "规格",
    "颜色",
    "面料",
    "面料-涤棉成分",
    "款式",
    "加标方式",
    "尺寸类型",
    "数量",
    "行备注",
    "计划发货日期",
    "包装方式",
    "是否绣花",
    "相似分数",
)

STRING_FIELD_NAMES: tuple[str, ...] = FINAL_FIELD_NAMES[:-1]


@dataclass(frozen=True)
class FinalResult:
    values: dict[str, str | float]

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "FinalResult":
        missing = [field for field in FINAL_FIELD_NAMES if field not in values]
        extra = [field for field in values if field not in FINAL_FIELD_NAMES]
        if missing or extra:
            raise ValueError(f"Invalid final result fields: missing={missing}, extra={extra}")

        normalized: dict[str, str | float] = {}
        for field in STRING_FIELD_NAMES:
            value = values[field]
            normalized[field] = "" if value is None else str(value)

        score = values["相似分数"]
        if score is None:
            raise ValueError("相似分数 must not be null")
        normalized["相似分数"] = float(score)
        return cls(normalized)

    def to_json_dict(self) -> dict[str, str | float]:
        return {field: self.values[field] for field in FINAL_FIELD_NAMES}
