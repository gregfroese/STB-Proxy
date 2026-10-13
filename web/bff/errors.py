"""The one error envelope every BFF route returns (spec 1.2)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        {"error": exc.message, "code": exc.code},
        status_code=exc.status,
    )


def unauthorized(message: str = "Sign in required.") -> ApiError:
    return ApiError(401, "unauthorized", message)


def session_invalid() -> ApiError:
    return ApiError(401, "session_invalid", "Your credentials are no longer valid.")


def proxy_unreachable() -> ApiError:
    return ApiError(502, "proxy_unreachable", "STB-Proxy is unreachable right now.")


def proxy_error() -> ApiError:
    return ApiError(502, "proxy_error", "STB-Proxy returned an error.")


def all_tuners_busy() -> ApiError:
    return ApiError(503, "all_tuners_busy", "All tuners are busy.")


def not_found(message: str = "Channel not found.") -> ApiError:
    return ApiError(404, "not_found", message)
