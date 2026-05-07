import logging
import re
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from jose import jwt, JWTError

from config import settings

logger = logging.getLogger(__name__)

_E164_RE = re.compile(r"\+\d{10,15}")
_PHONE_PARAM_RE = re.compile(r"((?:phone|tel)[=:][^&\s]{3,})", re.IGNORECASE)
_PII_FIELD_NAMES = {"phone", "first_name", "last_name", "email", "tel"}


def _scrub_query(qs: str) -> str:
    return _PHONE_PARAM_RE.sub(lambda m: m.group(0).split("=")[0] + "=***", qs)


def _scrub_path(path: str) -> str:
    return _E164_RE.sub("***", path)


class PIILogFilter(logging.Filter):
    """Redact E.164 phone numbers and PII field values from all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _E164_RE.sub("***REDACTED***", record.msg)
            record.msg = _PHONE_PARAM_RE.sub(lambda m: m.group(0).split("=")[0] + "=***", record.msg)
        for key in _PII_FIELD_NAMES:
            if key in record.__dict__ and record.__dict__[key]:
                record.__dict__[key] = "***"
        return True


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        user_id = self._extract_user_id(request)

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": _scrub_path(request.url.path),
                "query": _scrub_query(str(request.url.query)),
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
            },
        )

        return response

    def _extract_user_id(self, request: Request) -> int | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return int(payload.get("sub", 0)) or None
        except JWTError:
            return None
