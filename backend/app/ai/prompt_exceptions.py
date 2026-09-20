from app.core.exceptions import ApplicationError


class PromptNotFoundError(ApplicationError):
    def __init__(
        self,
        prompt_name: str,
        version: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=404,
            code="PROMPT_NOT_FOUND",
            message=f"Prompt '{prompt_name}' with version '{version}' not found.",
            headers=headers,
        )


class PromptVariableMissingError(ApplicationError):
    def __init__(
        self,
        prompt_name: str,
        version: str,
        missing_variables: list[str] | set[str],
        headers: dict[str, str] | None = None,
    ) -> None:
        missing_sorted = sorted(list(missing_variables))
        missing_str = ", ".join(missing_sorted)
        super().__init__(
            status_code=400,
            code="MISSING_PROMPT_VARIABLE",
            message=(
                f"Missing required variable(s) [{missing_str}] for prompt "
                f"'{prompt_name}' version '{version}'."
            ),
            headers=headers,
        )
        self.missing_variables = missing_sorted
