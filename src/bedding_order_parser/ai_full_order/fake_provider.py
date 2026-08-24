"""In-memory provider used only by whole-order contract tests."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES, SCHEMA_VERSION


class FakeFullOrderProvider:
    """Return controlled structured dictionaries without creating network clients."""

    def __init__(self, scenario: str = "normal") -> None:
        self.scenario = scenario
        self.extraction_call_count = 0
        self.structure_call_count = 0
        self.network_call_count = 0

    def resolve_structure(self, _manifest: Mapping[str, Any]) -> dict[str, str]:
        self.structure_call_count += 1
        return {"status": "offline_fake"}

    def extract(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.extraction_call_count += 1
        payload = _normal_response(request)
        if self.scenario == "normal":
            return payload
        record = payload["records"][0]
        if self.scenario == "missing_field":
            record["fields"].pop("物料名称")
        elif self.scenario == "extra_field":
            record["fields"]["额外字段"] = _empty_field()
        elif self.scenario == "wrong_type":
            payload["record_count"] = "one"
        elif self.scenario == "invalid_enum":
            record["fields"]["物料名称"]["extraction_status"] = "guessed"
        elif self.scenario == "cross_scope":
            target = next(item for item in request["evidence_catalog"] if item["scope_id"] != record["scope_id"])
            _set_extracted_field(record, target)
        elif self.scenario == "forged_cell":
            record["fields"]["物料名称"]["evidence_references"] = ["forged:evidence"]
        elif self.scenario == "material_code_injection":
            record["fields"]["物料编码"] = _empty_field()
        elif self.scenario == "similarity_score_injection":
            record["fields"]["相似分数"] = _empty_field()
        else:
            raise ValueError(f"Unsupported fake scenario: {self.scenario}")
        return payload


class FakeV2CandidateProvider:
    """Offline sparse-candidate source for V2 contract and provenance tests."""

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        layout_payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.payload = dict(payload)
        self.layout_payload = dict(layout_payload) if layout_payload is not None else None
        self.extraction_call_count = 0
        self.structure_call_count = 0
        self.network_call_count = 0
        self.requests: list[dict[str, Any]] = []

    def extract(self, request: Mapping[str, Any]) -> dict[str, Any]:
        self.extraction_call_count += 1
        self.requests.append(copy.deepcopy(dict(request)))
        return copy.deepcopy(self.payload)

    def extract_v2(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self.extract(request)

    def resolve_structure(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        self.structure_call_count += 1
        if self.layout_payload is not None:
            return copy.deepcopy(self.layout_payload)
        return {
            "layout_contract_version": str(manifest.get("layout_contract_version", "2.0")),
            "status": "ambiguous",
            "decisions": [
                {
                    "sheet_id": str(item.get("sheet_id", "")),
                    "role": "unresolved",
                    "candidate_id": "",
                    "reason": "insufficient_structure",
                }
                for item in manifest.get("unresolved_sheets", [])
            ],
        }


def _normal_response(request: Mapping[str, Any]) -> dict[str, Any]:
    evidence_by_id = {item["evidence_id"]: item for item in request["evidence_catalog"]}
    records: list[dict[str, Any]] = []
    for requested in request["records"]:
        fields = {name: _empty_field() for name in AI_BUSINESS_FIELD_NAMES}
        record_evidence = [evidence_by_id[evidence_id] for evidence_id in requested["evidence_ids"]]
        item_evidence = [item for item in record_evidence if str(item["cell_range"]).startswith("B")]
        first_evidence = item_evidence[-1] if item_evidence else record_evidence[-1]
        _set_extracted_field({"fields": fields}, first_evidence)
        records.append(
            {
                "record_local_id": requested["record_local_id"],
                "source_record_id": requested["source_record_id"],
                "scope_id": requested["scope_id"],
                "fields": fields,
                "extraction_status": "partial",
                "warnings": [],
                "unresolved_fields": [name for name in AI_BUSINESS_FIELD_NAMES if name != "物料名称"],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "parse_mode": "ai_enhanced",
        "source_file_sha256": request["source_file_sha256"],
        "provider": "fake_provider",
        "model": "offline-test",
        "request_id": "fake-request-1",
        "records": records,
        "record_count": len(records),
        "warnings": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "latency_ms": 0,
        "attempt_count": 0,
    }


def _empty_field() -> dict[str, Any]:
    return {
        "value": "",
        "original_value": "",
        "evidence_references": [],
        "extraction_status": "source_not_provided",
        "reason": "",
    }


def _set_extracted_field(record: Mapping[str, Any], evidence: Mapping[str, Any]) -> None:
    field = record["fields"]["物料名称"]
    field.update(
        {
            "value": str(evidence["normalized_text"]),
            "original_value": str(evidence["original_text"]),
            "evidence_references": [str(evidence["evidence_id"])],
            "extraction_status": "extracted",
            "reason": "合成证据包含该文本。",
        }
    )
