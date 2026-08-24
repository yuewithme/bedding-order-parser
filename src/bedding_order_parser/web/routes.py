"""HTTP routes for the dependency-free local web interface."""

from __future__ import annotations

import json
import mimetypes
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from bedding_order_parser.web.ai_advisory import (
    AIAdvisoryConflict,
    AIAdvisoryError,
    AIAdvisoryUnavailable,
)
from bedding_order_parser.web.services import MAX_UPLOAD_BYTES, WebJobError
from bedding_order_parser.ai_full_order.revisions import (
    RevisionConflict,
    RevisionError,
)


class WebRequestHandler(BaseHTTPRequestHandler):
    """Serve the single-page application and its local JSON API."""

    server_version = "BeddingOrderParser/1.0"

    @property
    def service(self):
        return self.server.service

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/health":
                self._send_json(
                    {
                        "status": "ok",
                        "accepting_jobs": bool(self.service.accepting),
                    }
                )
                return
            if path == "/":
                self._send_file(
                    self.server.template_path, "text/html; charset=utf-8"
                )
                return
            if path.startswith("/static/"):
                self._serve_static(path.removeprefix("/static/"))
                return
            if path == "/api/capabilities":
                payload = self.service.capabilities()
                payload["runtime"] = dict(self.server.runtime_identity)
                self._send_json(payload)
                return
            if path == "/api/ai-enhanced/preflight":
                self._send_json(self.service.ai_enhanced_preflight())
                return
            if path == "/api/jobs":
                self._send_json({"jobs": self.service.list_jobs()})
                return
            if path.startswith("/api/jobs/"):
                self._serve_job_route(path)
                return
            self._send_json({"error": "页面不存在。"}, HTTPStatus.NOT_FOUND)
        except WebJobError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except AIAdvisoryError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            self._send_json(
                {"error": "本地服务暂时无法完成请求。"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/jobs/") and path.endswith("/ai-review/revisions"):
            self._serve_ai_revision(path)
            return
        if path.startswith("/api/jobs/") and path.endswith("/reprocess-standard"):
            self._serve_standard_reprocess(path)
            return
        if path.startswith("/api/jobs/") and "/ai-actions/" in path:
            self._serve_ai_job_action(path)
            return
        if path.startswith("/api/tasks/") and path.endswith("/ai-enhance"):
            self._serve_ai_enhance(path)
            return
        if path != "/api/jobs":
            self._send_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return
        try:
            file_name, content, parse_mode = self._parse_upload()
            job = self.service.create_job(file_name, content, parse_mode=parse_mode)
            self.service.start_job(job["id"])
            self._send_json(job, HTTPStatus.CREATED)
        except WebJobError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            self._send_json(
                {"error": "文件上传失败，请重新选择。"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _serve_ai_revision(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if (
            len(parts) != 5
            or parts[:2] != ["api", "jobs"]
            or parts[3:] != ["ai-review", "revisions"]
        ):
            self._send_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json_body()
            result = self.service.revise_ai_result(parts[2], payload)
            status = HTTPStatus.OK if result["revision"]["reused"] else HTTPStatus.CREATED
            self._send_json(result, status)
        except RevisionConflict as exc:
            self._send_json(
                {"error": str(exc), "code": "REVISION_STALE"},
                HTTPStatus.CONFLICT,
            )
        except (RevisionError, WebJobError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except (TypeError, ValueError, json.JSONDecodeError):
            self._send_json(
                {"error": "结果修订请求格式不正确。"},
                HTTPStatus.BAD_REQUEST,
            )
        except Exception:
            self._send_json(
                {"error": "结果修订暂时无法完成，原结果保持不变。"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _serve_ai_job_action(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 5 or parts[:2] != ["api", "jobs"] or parts[3] != "ai-actions":
            self._send_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return
        job_id, action = parts[2], parts[4]
        try:
            if action == "retry":
                result = self.service.retry_missing_chunks(job_id)
            elif action == "keep-failed":
                result = self.service.keep_failed(job_id)
            else:
                raise WebJobError("未知的AI任务操作。")
            self._send_json(result)
        except WebJobError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except (TypeError, ValueError, json.JSONDecodeError):
            self._send_json({"error": "AI任务操作格式不正确。"}, HTTPStatus.BAD_REQUEST)
        except Exception:
            self._send_json(
                {"error": "AI任务操作暂时无法完成，请稍后重试。"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _serve_standard_reprocess(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4 or parts[:2] != ["api", "jobs"] or parts[3] != "reprocess-standard":
            self._send_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return
        try:
            result = self.service.reprocess_ai_job_as_standard(
                parts[2], operation_id=self.headers.get("X-Idempotency-Key", "")
            )
            self._send_json(result, HTTPStatus.OK)
        except WebJobError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            self._send_json(
                {"error": "标准解析重新处理暂时无法完成，原AI任务保持不变。"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _serve_job_route(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 3:
            raise WebJobError("解析任务编号无效。")
        job_id = parts[2]
        if len(parts) == 3:
            self._send_json(self.service.get_job(job_id))
            return
        if parts[3] == "artifacts" and len(parts) == 6:
            kind, action = parts[4], parts[5]
            if action == "preview":
                self._send_json(self.service.get_preview(job_id, kind))
                return
            if action == "download":
                path = self.service.artifact_path(job_id, kind)
                self._send_download(path)
                return
        if parts[3] == "download-all" and len(parts) == 4:
            self._send_download(self.service.bundle_path(job_id))
            return
        if parts[3] == "ai-review" and len(parts) == 4:
            self._send_json(self.service.get_ai_review(job_id))
            return
        if parts[3] == "matches" and len(parts) == 4:
            self._send_json({"records": self.service.list_matches(job_id)})
            return
        if parts[3] == "matches" and len(parts) == 5:
            try:
                index = int(parts[4])
            except ValueError as exc:
                raise WebJobError("订单行编号无效。") from exc
            self._send_json(self.service.match_detail(job_id, index))
            return
        if (
            parts[3] == "matches"
            and len(parts) == 6
            and parts[5] == "ai-advisory"
        ):
            try:
                index = int(parts[4])
            except ValueError as exc:
                raise WebJobError("订单行编号无效。") from exc
            self._send_json(
                self.service.ai_advisory_status(job_id, index)
            )
            return
        raise WebJobError("未找到该任务内容。")

    def _serve_ai_enhance(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 4 or parts[:2] != ["api", "tasks"]:
            self._send_json({"error": "接口不存在。"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json_body()
            raw_index = payload.get("record_index")
            if isinstance(raw_index, bool):
                raise AIAdvisoryUnavailable("订单记录编号无效。")
            index = int(raw_index)
            result = self.service.start_ai_advisory(
                parts[2],
                index,
                payload,
            )
            status = (
                HTTPStatus.OK
                if result["state"] in {"completed", "cached"}
                else HTTPStatus.ACCEPTED
            )
            self._send_json(result, status)
        except AIAdvisoryConflict as exc:
            self._send_json(
                {
                    "error": {
                        "code": "AI_ADVISORY_BUSY",
                        "message": str(exc),
                    }
                },
                HTTPStatus.CONFLICT,
            )
        except AIAdvisoryUnavailable as exc:
            capabilities = self.service.capabilities()["llm"]
            status = (
                HTTPStatus.SERVICE_UNAVAILABLE
                if not capabilities["configured"]
                else HTTPStatus.BAD_REQUEST
            )
            self._send_json(
                {
                    "error": {
                        "code": "AI_ADVISORY_UNAVAILABLE",
                        "message": str(exc),
                    }
                },
                status,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            self._send_json(
                {
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "AI建议请求格式不正确。",
                    }
                },
                HTTPStatus.BAD_REQUEST,
            )

    def _serve_static(self, relative: str) -> None:
        if not relative or "/" in relative or "\\" in relative:
            self._send_json({"error": "静态资源不存在。"}, HTTPStatus.NOT_FOUND)
            return
        static_root = self.server.static_root.resolve()
        path = (static_root / relative).resolve()
        if path.parent != static_root or not path.is_file():
            self._send_json({"error": "静态资源不存在。"}, HTTPStatus.NOT_FOUND)
            return
        content_type = (
            mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        )
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
        }:
            content_type += "; charset=utf-8"
        self._send_file(path, content_type)

    def _parse_upload(self) -> tuple[str, bytes, str]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise WebJobError("请使用文件上传方式提交 Excel。")
        raw_length = self.headers.get("Content-Length", "")
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise WebJobError("无法读取上传文件大小。") from exc
        if content_length <= 0:
            raise WebJobError("上传内容为空。")
        if content_length > MAX_UPLOAD_BYTES + 1024 * 1024:
            raise WebJobError("文件超过 25 MB，请确认后重新上传。")
        body = self.rfile.read(content_length)
        message = BytesParser(policy=policy.default).parsebytes(
            (
                f"Content-Type: {content_type}\r\n"
                "MIME-Version: 1.0\r\n\r\n"
            ).encode("utf-8")
            + body
        )
        if not message.is_multipart():
            raise WebJobError("上传内容格式不正确。")
        file_name = ""
        content: bytes | None = None
        parse_mode = "standard"
        for part in message.iter_parts():
            field_name = part.get_param(
                "name", header="content-disposition"
            )
            if field_name == "file":
                file_name = part.get_filename() or ""
                content = part.get_payload(decode=True)
            elif field_name == "parse_mode":
                parse_mode = str(part.get_content() or "").strip() or "standard"
        if file_name and content is not None:
            return file_name, content, parse_mode
        raise WebJobError("未收到 Excel 文件。")

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "")
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if content_length <= 0 or content_length > 16 * 1024:
            raise ValueError("invalid JSON body size")
        payload = json.loads(
            self.rfile.read(content_length).decode("utf-8")
        )
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _send_json(
        self, payload: Any, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_download(self, path: Path) -> None:
        body = path.read_bytes()
        encoded_name = "".join(
            character if character.isascii() and character.isalnum() else "_"
            for character in path.name
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{encoded_name}\"; "
            f"filename*=UTF-8''{self._quote_filename(path.name)}",
        )
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _quote_filename(name: str) -> str:
        from urllib.parse import quote

        return quote(name)

    def log_message(self, format: str, *args: object) -> None:
        # Keep the local console quiet and avoid echoing business filenames.
        return
