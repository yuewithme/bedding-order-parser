"""Safe, local build facts for identifying the desktop runtime."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from bedding_order_parser.ai_full_order.contracts import V2_CONTRACT_VERSION


_UI_VERSION_PATTERN = re.compile(
    r'AI_FULL_ORDER_UI_VERSION\s*=\s*"(?P<version>[^"]+)"'
)
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True)
class RuntimeIdentity:
    """Publicly safe version facts without paths, configuration, or machine data."""

    application_version: str
    build_commit_short: str
    ui_asset_version: str
    ui_asset_sha256_short: str
    ai_contract_version: str

    def to_public_dict(self) -> dict[str, str]:
        return asdict(self)


def build_runtime_identity(*, project_root: Path, asset_root: Path) -> RuntimeIdentity:
    """Read only checked-in build facts needed to identify the local UI instance."""

    app_js = asset_root / "static" / "app.js"
    source = app_js.read_text(encoding="utf-8")
    match = _UI_VERSION_PATTERN.search(source)
    ui_version = match.group("version") if match else "unknown"
    return RuntimeIdentity(
        application_version="0.1.0",
        build_commit_short=_build_commit_short(project_root),
        ui_asset_version=ui_version,
        ui_asset_sha256_short=hashlib.sha256(app_js.read_bytes()).hexdigest()[:12],
        ai_contract_version=V2_CONTRACT_VERSION,
    )


def _build_commit_short(project_root: Path) -> str:
    configured = os.environ.get("BEDDING_ORDER_PARSER_BUILD_COMMIT", "").strip().lower()
    if _COMMIT_PATTERN.fullmatch(configured):
        return configured[:12]
    git_dir = project_root / ".git"
    head = git_dir / "HEAD"
    try:
        reference = head.read_text(encoding="ascii").strip()
        if reference.startswith("ref: "):
            candidate = (git_dir / reference.removeprefix("ref: ")).read_text(
                encoding="ascii"
            ).strip()
        else:
            candidate = reference
    except OSError:
        return "unavailable"
    return candidate[:12] if _COMMIT_PATTERN.fullmatch(candidate) else "unavailable"
