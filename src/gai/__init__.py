"""gai - Google Gemini prompting script with flexible CLI, templating, and configuration."""

from .config import load_effective_config
from .exceptions import CliUsageError, ConfigError, GaiError, GenerationError, TemplateError
from .generation import generate, prepare_generate_content_config_dict, prepare_prompt_contents
from .templates import render_template_string

__version__ = "0.1.9"

__all__ = [
    "CliUsageError",
    "ConfigError",
    "GaiError",
    "GenerationError",
    "TemplateError",
    "__version__",
    "generate",
    "load_effective_config",
    "prepare_generate_content_config_dict",
    "prepare_prompt_contents",
    "render_template_string",
]
