"""Injectable JSON HTTP transport for offline-testable LLM providers."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class TransportError(RuntimeError):
    """Base transport failure with no request or credential echo."""


class TransportTimeout(TransportError):
    """The provider did not respond within the configured deadline."""


class TransportConnectionError(TransportError):
    """The provider could not be reached."""


@dataclass(frozen=True, repr=False)
class JSONHTTPRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes
    timeout_seconds: float

    def __repr__(self) -> str:
        return (
            "JSONHTTPRequest("
            f"method={self.method!r}, "
            f"url={self.url!r}, "
            f"header_names={sorted(self.headers)!r}, "
            f"body_bytes={len(self.body)}, "
            f"timeout_seconds={self.timeout_seconds!r}"
            ")"
        )


@dataclass(frozen=True)
class JSONHTTPResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    elapsed_ms: int


class JSONTransport(Protocol):
    def send(self, request: JSONHTTPRequest) -> JSONHTTPResponse: ...


class UrllibJSONTransport:
    """Small production transport with explicit timeout and HTTP responses."""

    def send(self, request: JSONHTTPRequest) -> JSONHTTPResponse:
        started = time.monotonic()
        raw_request = Request(
            request.url,
            data=request.body,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with urlopen(
                raw_request, timeout=request.timeout_seconds
            ) as response:
                return JSONHTTPResponse(
                    status_code=int(response.status),
                    headers=_normalized_headers(response.headers),
                    body=response.read(),
                    elapsed_ms=_elapsed_ms(started),
                )
        except HTTPError as exc:
            return JSONHTTPResponse(
                status_code=int(exc.code),
                headers=_normalized_headers(exc.headers),
                body=exc.read(),
                elapsed_ms=_elapsed_ms(started),
            )
        except (TimeoutError, socket.timeout) as exc:
            raise TransportTimeout(
                "The LLM provider request timed out."
            ) from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise TransportTimeout(
                    "The LLM provider request timed out."
                ) from exc
            raise TransportConnectionError(
                "The LLM provider connection failed."
            ) from exc
        except OSError as exc:
            raise TransportConnectionError(
                "The LLM provider connection failed."
            ) from exc


def _normalized_headers(headers: object) -> dict[str, str]:
    if headers is None:
        return {}
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    return {str(key).lower(): str(value) for key, value in items()}


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))
