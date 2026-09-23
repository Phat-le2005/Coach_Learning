import time
from collections import defaultdict
from threading import Lock
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
import jwt

from app.ai.exceptions import AIRateLimitError
from app.core.config import Settings, get_settings


class AIRateLimiter:
    """In-memory rate limiter tracking minute and daily quotas per user for AI endpoints.
    
    Guarantees:
    - Enforces max requests per minute (e.g. 20 req/min).
    - Enforces max requests per day (e.g. 100 req/day).
    - Raises AIRateLimitError (HTTP 429) when limits are exceeded.
    - Completely separate from Learning Core: Core endpoints NEVER check this limiter,
      ensuring practice sessions, exam submissions, and mastery calculations are NEVER blocked.
    """

    def __init__(
        self,
        default_minute_limit: int = 20,
        default_daily_limit: int = 100,
    ) -> None:
        self.default_minute_limit = default_minute_limit
        self.default_daily_limit = default_daily_limit
        self._lock = Lock()
        # Mapping: str(user_id) -> list[float] (timestamps of requests)
        self._request_timestamps: dict[str, list[float]] = defaultdict(list)

    def check_rate_limit(
        self,
        user_id: UUID | str,
        *,
        minute_limit: int | None = None,
        daily_limit: int | None = None,
    ) -> None:
        """Check whether user exceeded rate limit.
        
        Raises:
            AIRateLimitError: If minute or daily quota exceeded.
        """
        uid = str(user_id)
        max_min = minute_limit if minute_limit is not None else self.default_minute_limit
        max_day = daily_limit if daily_limit is not None else self.default_daily_limit
        now = time.time()

        with self._lock:
            timestamps = self._request_timestamps[uid]
            # Prune timestamps older than 24 hours (86400 seconds)
            day_cutoff = now - 86400.0
            timestamps = [ts for ts in timestamps if ts >= day_cutoff]
            self._request_timestamps[uid] = timestamps

            # 1. Check minute window (last 60 seconds)
            min_cutoff = now - 60.0
            recent_minute_requests = sum(1 for ts in timestamps if ts >= min_cutoff)
            if recent_minute_requests >= max_min:
                raise AIRateLimitError(
                    message=f"AI rate limit exceeded: maximum {max_min} requests per minute allowed.",
                    headers={"Retry-After": "60"},
                )

            # 2. Check 24-hour daily window
            if len(timestamps) >= max_day:
                raise AIRateLimitError(
                    message=f"AI daily quota exceeded: maximum {max_day} requests per day allowed.",
                    headers={"Retry-After": "86400"},
                )

            # Record current request
            timestamps.append(now)

    def reset(self) -> None:
        """Reset all rate limiter state (useful in tests)."""
        with self._lock:
            self._request_timestamps.clear()


# Global singleton instance
ai_rate_limiter = AIRateLimiter()


def get_ai_rate_limiter() -> AIRateLimiter:
    return ai_rate_limiter


def require_ai_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    limiter: Annotated[AIRateLimiter, Depends(get_ai_rate_limiter)],
) -> None:
    """FastAPI dependency to rate limit AI endpoints."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key.get_secret_value(),
                algorithms=["HS256"],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )
            user_id = payload.get("sub")
            if user_id:
                limiter.check_rate_limit(
                    user_id,
                    minute_limit=settings.ai_rate_limit_per_minute,
                    daily_limit=settings.ai_daily_requests_limit_per_student,
                )
        except AIRateLimitError:
            raise
        except Exception:
            pass
