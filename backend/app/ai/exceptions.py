from app.core.exceptions import ApplicationError


class AIServiceUnavailableError(ApplicationError):
    def __init__(
        self,
        message: str = "AI service is currently unavailable.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=503,
            code="AI_SERVICE_UNAVAILABLE",
            message=message,
            headers=headers,
        )


class AIRateLimitError(ApplicationError):
    def __init__(
        self,
        message: str = "AI service rate limit exceeded. Please try again later.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=429,
            code="AI_RATE_LIMIT_EXCEEDED",
            message=message,
            headers=headers,
        )


class AITimeoutError(ApplicationError):
    def __init__(
        self,
        message: str = "AI gateway request timed out.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=504,
            code="AI_GATEWAY_TIMEOUT",
            message=message,
            headers=headers,
        )


class AIConfigurationError(ApplicationError):
    def __init__(
        self,
        message: str = "AI configuration error.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=500,
            code="AI_CONFIGURATION_ERROR",
            message=message,
            headers=headers,
        )
