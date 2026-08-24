"""Safely write paired business-result and parse-report JSON files."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from bedding_order_parser.diagnostics.models import ParseReport
from bedding_order_parser.exceptions import OutputFileError
from bedding_order_parser.models.final_result import FinalResult


def default_report_path(result_path: str | Path) -> Path:
    path = Path(result_path)
    return path.with_name(f"{path.stem}_parse_report.json")


def write_parse_outputs(
    records: list[FinalResult],
    report: ParseReport,
    result_path: Path,
    report_path: Path | None = None,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    result = result_path.expanduser().resolve()
    parse_report = (report_path or default_report_path(result)).expanduser().resolve()
    if result == parse_report:
        raise OutputFileError("Business result and parse report paths must be different.")
    if not overwrite:
        existing = [path for path in (result, parse_report) if path.exists()]
        if existing:
            raise OutputFileError(f"Output file already exists: {existing[0]}")

    result.parent.mkdir(parents=True, exist_ok=True)
    parse_report.parent.mkdir(parents=True, exist_ok=True)
    result_payload = [record.to_json_dict() for record in records]
    report_payload = report.to_json_dict()

    temporary_files: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    installed: set[Path] = set()
    try:
        temporary_files[result] = _write_temporary_json(result, result_payload)
        temporary_files[parse_report] = _write_temporary_json(parse_report, report_payload)

        if overwrite:
            for destination in (result, parse_report):
                if destination.exists():
                    backup = _reserve_temporary_path(destination, ".bak")
                    os.replace(destination, backup)
                    backups[destination] = backup

        for destination in (result, parse_report):
            os.replace(temporary_files[destination], destination)
            installed.add(destination)

    except Exception as exc:
        for destination in installed:
            destination.unlink(missing_ok=True)
        for destination, backup in backups.items():
            if backup.exists():
                os.replace(backup, destination)
        for temporary in temporary_files.values():
            temporary.unlink(missing_ok=True)
        for backup in backups.values():
            backup.unlink(missing_ok=True)
        if isinstance(exc, OutputFileError):
            raise
        raise OutputFileError("Failed to write paired JSON outputs safely.") from exc

    for backup in backups.values():
        backup.unlink(missing_ok=True)
    return result, parse_report


def _write_temporary_json(destination: Path, payload: Any) -> Path:
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            temp_name = temp_file.name
            json.dump(payload, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
        return Path(temp_name)
    except Exception:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise


def _reserve_temporary_path(destination: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(dir=destination.parent, suffix=suffix)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path
