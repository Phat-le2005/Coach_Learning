import re
from pathlib import Path
from typing import Any

from app.ai.prompt_exceptions import (
    PromptNotFoundError,
    PromptVariableMissingError,
)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class PromptRegistry:
    """Registry and template engine for versioned pedagogical AI prompts.
    
    Guarantees:
    - Prompts do NOT hard-code curriculum facts; all academic knowledge is injected via variables.
    - Strict validation of required variables; missing variables fail with explicit errors.
    - Template caching for zero-overhead repeat rendering.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or PROMPTS_DIR
        self._cache: dict[tuple[str, str], tuple[str, set[str]]] = {}

    def _load_template(self, name: str, version: str) -> tuple[str, set[str]]:
        cache_key = (name, version)
        if cache_key in self._cache:
            return self._cache[cache_key]

        prompt_dir = self.base_dir / name
        if not prompt_dir.is_dir():
            raise PromptNotFoundError(prompt_name=name, version=version)

        template_file = prompt_dir / f"{version}.txt"
        if not template_file.is_file():
            raise PromptNotFoundError(prompt_name=name, version=version)

        content = template_file.read_text(encoding="utf-8")
        required_vars = set(VARIABLE_PATTERN.findall(content))

        self._cache[cache_key] = (content, required_vars)
        return content, required_vars

    def get_required_variables(self, name: str, version: str = "v1") -> set[str]:
        """Return the set of all required variable names for the given prompt and version."""
        _, required_vars = self._load_template(name, version)
        return set(required_vars)

    def list_prompts(self) -> list[str]:
        """List all registered prompt names discovered in the prompts directory."""
        if not self.base_dir.is_dir():
            return []
        return sorted([d.name for d in self.base_dir.iterdir() if d.is_dir()])

    def list_versions(self, name: str) -> list[str]:
        """List all available versions for a prompt name."""
        prompt_dir = self.base_dir / name
        if not prompt_dir.is_dir():
            raise PromptNotFoundError(prompt_name=name, version="*")
        versions: list[str] = []
        for file in prompt_dir.glob("*.txt"):
            versions.append(file.stem)
        return sorted(versions)

    def get_prompt(
        self,
        name: str,
        version: str = "v1",
        variables: dict[str, Any] | None = None,
    ) -> str:
        """Load, validate, and render a prompt with variables.
        
        Raises:
            PromptNotFoundError: If prompt name or version does not exist.
            PromptVariableMissingError: If any required variable is missing or None.
        """
        template_text, required_vars = self._load_template(name, version)
        provided = variables or {}

        missing: set[str] = set()
        for var in required_vars:
            if var not in provided or provided[var] is None:
                missing.add(var)

        if missing:
            raise PromptVariableMissingError(
                prompt_name=name,
                version=version,
                missing_variables=missing,
            )

        def _replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            val = provided[key]
            return str(val)

        return VARIABLE_PATTERN.sub(_replacer, template_text)


# Default singleton instance
default_prompt_registry = PromptRegistry()
