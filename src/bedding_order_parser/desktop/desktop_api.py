"""Small pywebview bridge for reliable Save As downloads."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import webview

from bedding_order_parser.web.services import JobService, WebJobError


class DesktopApi:
    """Expose only validated artifact copies to the desktop page."""

    def __init__(self, service: JobService) -> None:
        self.service = service
        self.window: Any | None = None

    def attach_window(self, window: Any) -> None:
        self.window = window

    def save_artifact(self, job_id: str, kind: str) -> dict[str, object]:
        if self.window is None:
            return {"saved": False, "message": "桌面窗口尚未就绪。"}
        try:
            source = (
                self.service.bundle_path(job_id)
                if kind == "zip"
                else self.service.artifact_path(job_id, kind)
            )
        except WebJobError as exc:
            return {"saved": False, "message": str(exc)}
        selected = self.window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=source.name,
        )
        if not selected:
            return {"saved": False, "cancelled": True}
        destination = Path(
            selected[0] if isinstance(selected, (list, tuple)) else selected
        ).resolve()
        if destination.exists():
            confirmed = self.window.create_confirmation_dialog(
                "确认覆盖",
                f"文件“{destination.name}”已存在，是否覆盖？",
            )
            if not confirmed:
                return {"saved": False, "cancelled": True}
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return {
            "saved": True,
            "file_name": destination.name,
            "message": "文件已保存。",
        }
