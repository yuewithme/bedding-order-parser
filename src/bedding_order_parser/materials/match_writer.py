"""Atomic output writer for the material matching prototype."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.materials.hybrid_matcher import HybridMatchResult


CANDIDATES_NAME = "material_match_candidates.json"
SUMMARY_NAME = "material_match_summary.json"


class MatchWriterError(BeddingOrderParserError):
    """Raised when prototype outputs cannot be committed atomically."""


@dataclass(frozen=True)
class MatchOutputPaths:
    output_dir: Path
    candidates_path: Path
    summary_path: Path


def write_match_outputs(
    result: HybridMatchResult,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> MatchOutputPaths:
    """Write exactly two JSON files through a temporary sibling directory."""
    target = Path(output_dir).expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise MatchWriterError(
            f"Prototype output already exists; pass --overwrite: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    backup_dir: Path | None = None
    temp_dir.mkdir()
    try:
        _write_json(temp_dir / CANDIDATES_NAME, result.candidates_payload)
        _write_json(temp_dir / SUMMARY_NAME, result.summary_payload)
        if target.exists():
            backup_dir = target.parent / f".{target.name}.{uuid.uuid4().hex}.backup"
            target.rename(backup_dir)
        temp_dir.rename(target)
        if backup_dir is not None:
            shutil.rmtree(backup_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if backup_dir is not None and backup_dir.exists() and not target.exists():
            backup_dir.rename(target)
        raise
    return MatchOutputPaths(
        output_dir=target,
        candidates_path=target / CANDIDATES_NAME,
        summary_path=target / SUMMARY_NAME,
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
