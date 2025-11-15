"""Custom exceptions for gai."""


class GaiError(Exception):
    """Base exception for all gai errors."""


class ConfigError(GaiError):
    """Exception raised for configuration-related errors."""


class TemplateError(GaiError):
    """Exception raised for template rendering errors."""


class TemplateResolutionError(TemplateError):
    """Base exception for template resolution errors."""


class TemplateNotFoundError(TemplateResolutionError):
    """Exception raised when a template cannot be found in any tier."""

    def __init__(self, logical_name: str, searched_roots: list[str]):
        self.logical_name = logical_name
        self.searched_roots = searched_roots
        roots_summary = ", ".join(searched_roots) if searched_roots else "no template roots configured"
        super().__init__(f"Template '{logical_name}' not found. Searched roots: {roots_summary}")


class TemplateAmbiguityError(TemplateResolutionError):
    """Exception raised when multiple templates match a logical name in the same tier."""

    def __init__(self, logical_name: str, tier: str, candidates: list[tuple[str, str]]):
        self.logical_name = logical_name
        self.tier = tier
        self.candidates = candidates
        candidate_list = "\n  ".join(f"{path} (extension: {ext})" for path, ext in candidates)
        super().__init__(
            f"Ambiguous template name '{logical_name}' in tier '{tier}'. "
            f"Multiple candidates found:\n  {candidate_list}\n"
            f"Use a more specific path (e.g., 'path/name') or explicit extension (e.g., 'name.j2')."
        )


class CliUsageError(GaiError):
    """Exception raised for CLI usage errors."""


class GenerationError(GaiError):
    """Exception raised for API generation errors."""
