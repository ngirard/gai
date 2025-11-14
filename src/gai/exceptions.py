"""Custom exceptions for gai."""


class GaiError(Exception):
    """Base exception for all gai errors."""



class ConfigError(GaiError):
    """Exception raised for configuration-related errors."""



class TemplateError(GaiError):
    """Exception raised for template rendering errors."""



class CliUsageError(GaiError):
    """Exception raised for CLI usage errors."""



class GenerationError(GaiError):
    """Exception raised for API generation errors."""

