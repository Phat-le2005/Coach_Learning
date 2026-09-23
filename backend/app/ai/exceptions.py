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


class AIOutputValidationError(ApplicationError):
    def __init__(
        self,
        message: str = "AI structured output failed validation against expected schema.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=422,
            code="AI_OUTPUT_VALIDATION_ERROR",
            message=message,
            headers=headers,
        )


class AIInvalidJSONError(AIOutputValidationError):
    def __init__(
        self,
        message: str = "AI response contains invalid JSON syntax.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            headers=headers,
        )
        self.code = "AI_INVALID_JSON"


class AIFakeCurriculumCodeError(ApplicationError):
    def __init__(
        self,
        message: str = "AI proposed or referenced nonexistent/hallucinated curriculum codes.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=422,
            code="AI_FAKE_CURRICULUM_CODE",
            message=message,
            headers=headers,
        )


class AIUnknownActionError(ApplicationError):
    def __init__(
        self,
        message: str = "Unknown AI action requested. Action does not exist in registry.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=400,
            code="AI_UNKNOWN_ACTION",
            message=message,
            headers=headers,
        )


class AIActionNotAllowedError(ApplicationError):
    def __init__(
        self,
        message: str = "Action is not permitted for this AI task type or tool policy.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=403,
            code="AI_ACTION_NOT_ALLOWED",
            message=message,
            headers=headers,
        )


class AIForbiddenMutationError(ApplicationError):
    def __init__(
        self,
        message: str = "AI is forbidden from performing this mutation to protected system state.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=403,
            code="AI_FORBIDDEN_MUTATION",
            message=message,
            headers=headers,
        )


class AIPromptInjectionError(ApplicationError):
    def __init__(
        self,
        message: str = "Potential prompt injection or adversarial instruction detected in prompt.",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=400,
            code="AI_PROMPT_INJECTION_DETECTED",
            message=message,
            headers=headers,
        )
