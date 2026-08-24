"""Explicit, local-only CLI for bounded LLM provider diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

from bedding_order_parser.llm.contracts import LLMEnhancementRequest
from bedding_order_parser.llm.errors import LLMProviderError
from bedding_order_parser.llm.service import LLMService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bedding_order_parser.llm.diagnostics"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    connectivity = subparsers.add_parser("connectivity")
    connectivity.add_argument("--output", required=True, type=Path)

    advisory = subparsers.add_parser("advisory")
    advisory.add_argument("--input", required=True, type=Path)
    advisory.add_argument("--output", required=True, type=Path)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    service: LLMService | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    llm_service = service or LLMService()
    try:
        if args.command == "connectivity":
            result = llm_service.check_connectivity()
            payload = {
                "kind": "connectivity",
                "expected_text_match": result.text.strip() == "连接成功",
                "result": result.to_dict(),
            }
        else:
            request = _load_request(args.input)
            result = llm_service.enhance_record(request)
            payload = {
                "kind": "advisory",
                "result": result.to_dict(),
            }
        _write_json_atomic(args.output, payload)
        print(
            json.dumps(
                {
                    "status": "succeeded",
                    "kind": payload["kind"],
                    "output_written": True,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (LLMProviderError, OSError, ValueError, json.JSONDecodeError) as exc:
        error = (
            exc.to_dict()
            if isinstance(exc, LLMProviderError)
            else {
                "code": "diagnostic_input_error",
                "summary": str(exc),
                "retryable": False,
            }
        )
        _write_json_atomic(
            args.output,
            {"kind": args.command, "status": "failed", "error": error},
        )
        print(
            json.dumps(
                {
                    "status": "failed",
                    "kind": args.command,
                    "error_code": error["code"],
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        llm_service.close()


def _load_request(path: Path) -> LLMEnhancementRequest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Diagnostic request must be a JSON object.")
    return LLMEnhancementRequest(
        job_id=str(payload.get("job_id", "")),
        source_record_id=_string(payload, "source_record_id"),
        source_file=_string(payload, "source_file"),
        sheet_name=_string(payload, "sheet_name"),
        source_row=_string(payload, "source_row"),
        raw_evidence=_mapping(payload, "raw_evidence"),
        parsed_record=_mapping(payload, "parsed_record"),
        parse_diagnostics=_mapping(payload, "parse_diagnostics"),
        dictionary_validation=_mapping(
            payload, "dictionary_validation"
        ),
        top_candidates=_list_of_mappings(payload, "top_candidates"),
        enhancement_reason=_string(payload, "enhancement_reason"),
    )


def _string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string.")
    return value


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object.")
    return value


def _list_of_mappings(
    payload: dict[str, Any], name: str
) -> list[dict[str, Any]]:
    value = payload.get(name)
    if not isinstance(value, list) or not all(
        isinstance(item, dict) for item in value
    ):
        raise ValueError(f"{name} must be an array of objects.")
    return value


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
