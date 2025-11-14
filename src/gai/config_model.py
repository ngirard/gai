"""Configuration data models for type-safe config handling."""

from dataclasses import dataclass
from typing import Optional

from .exceptions import ConfigError


@dataclass
class Config:
    """Type-safe configuration for gai.

    Attributes:
        model: The Gemini model to use (e.g., "gemini-flash-latest")
        temperature: Controls randomness (0.0-2.0)
        response_mime_type: Output format (e.g., "text/plain", "application/json")
        max_output_tokens: Maximum tokens to generate (None for unlimited)
        system_instruction: System instruction template
        user_instruction: User instruction template
    """

    model: str
    temperature: float
    response_mime_type: str
    max_output_tokens: Optional[int]
    system_instruction: Optional[str]
    user_instruction: Optional[str]

    def __post_init__(self) -> None:
        """Validate configuration values after initialization."""
        self._validate()

    def _validate(self) -> None:
        """Validate configuration values.

        Raises:
            ConfigError: If any configuration value is invalid.
        """
        # Validate temperature range (Gemini API typically accepts 0.0-2.0)
        if not 0.0 <= self.temperature <= 2.0:
            raise ConfigError(f"temperature must be between 0.0 and 2.0, got {self.temperature}")

        # Validate max_output_tokens
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ConfigError(f"max_output_tokens must be positive, got {self.max_output_tokens}")

        # Validate model name is not empty
        if not self.model or not self.model.strip():
            raise ConfigError("model name cannot be empty")

        # Validate response_mime_type
        valid_mime_types = {"text/plain", "application/json"}
        if self.response_mime_type not in valid_mime_types:
            raise ConfigError(f"response_mime_type must be one of {valid_mime_types}, got '{self.response_mime_type}'")

    def to_dict(self) -> dict:
        """Convert config to dictionary for backward compatibility.

        Returns:
            Dictionary representation with kebab-case keys.
        """
        return {
            "model": self.model,
            "temperature": self.temperature,
            "response-mime-type": self.response_mime_type,
            "max-output-tokens": self.max_output_tokens,
            "system-instruction": self.system_instruction,
            "user-instruction": self.user_instruction,
        }

    @classmethod
    def from_dict(cls, config_dict: dict) -> "Config":
        """Create Config from dictionary with kebab-case keys.

        Args:
            config_dict: Dictionary with kebab-case keys

        Returns:
            Config instance
        """
        return cls(
            model=config_dict.get("model", "gemini-flash-latest"),
            temperature=config_dict.get("temperature", 0.1),
            response_mime_type=config_dict.get("response-mime-type", "text/plain"),
            max_output_tokens=config_dict.get("max-output-tokens"),
            system_instruction=config_dict.get("system-instruction"),
            user_instruction=config_dict.get("user-instruction"),
        )
