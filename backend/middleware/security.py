"""
Security middleware — rate limiting, CORS, security headers.
DO NOT MODIFY without explicit instruction.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

_RATE_LIMIT_RULES = {
    ("POST", "/auth/login"): ("login", 5, 900),
    ("POST", "/items/capture"): ("capture", 100, 60),
    ("GET", "/analytics/"): ("analytics", 60, 60),
}


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_origins: list[str], is_production: bool):
        super().__init__(app)
        self.allowed_origins = allowed_origins
        self.is_production = is_production

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin", "")

        # Short-circuit CORS preflight — browsers send OPTIONS before real requests
        if request.method == "OPTIONS":
            response = Response(status_code=200)
            if origin in self.allowed_origins or (not self.is_production and origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
                response.headers["Access-Control-Max-Age"] = "600"
            return response

        rate_limit_result = await self._check_rate_limit(request)
        if rate_limit_result is not None:
            return rate_limit_result

        response = await call_next(request)

        if origin in self.allowed_origins or (not self.is_production and origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response

    async def _check_rate_limit(self, request: Request) -> Response | None:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is None:
            return None

        key_prefix = None
        limit = None
        window = None

        path = request.url.path
        method = request.method

        if method == "POST" and path == "/auth/login":
            ip = request.client.host if request.client else "unknown"
            key_prefix = f"rl:login:{ip}"
            limit, window = 5, 900
        elif method == "POST" and path == "/items/capture":
            auth = request.headers.get("Authorization", "")
            identifier = auth[-20:] if auth else request.client.host
            key_prefix = f"rl:capture:{identifier}"
            limit, window = 100, 60
        elif method == "GET" and path.startswith("/analytics/"):
            auth = request.headers.get("Authorization", "")
            identifier = auth[-20:] if auth else request.client.host
            key_prefix = f"rl:analytics:{identifier}"
            limit, window = 60, 60

        if key_prefix is None:
            return None

        try:
            current = await redis_client.incr(key_prefix)
            if current == 1:
                await redis_client.expire(key_prefix, window)
            if current > limit:
                ttl = await redis_client.ttl(key_prefix)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={"Retry-After": str(max(ttl, 1))},
                )
        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")

        return None
