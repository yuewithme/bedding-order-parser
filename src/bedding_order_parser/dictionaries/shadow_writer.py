"""Write dictionary shadow comparison JSON safely."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from bedding_order_parser.dictionaries.shadow_models import ShadowReport
from bedding_order_parser.exceptions import OutputFileError


def write_shadow_report(
    report: ShadowReport,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    resolved = output_path.expanduser().resolve()
    if resolved.exists() and not overwrite:
        raise OutputFileError(f"Output file already exists: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)

    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=resolved.parent,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            temp_name = temp_file.name
            json.dump(report.to_json_dict(), temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
        os.replace(temp_name, resolved)
    except Exception as exc:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise OutputFileError(f"Failed to write dictionary shadow report: {resolved}") from exc

    return resolved
