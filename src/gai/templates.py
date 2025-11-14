"""Template handling for gai using Jinja2."""

import logging
from typing import Any, Optional

import jinja2

from .exceptions import TemplateError

logger = logging.getLogger(__name__)


def create_jinja_env() -> jinja2.Environment:
    """Creates and configures the global Jinja2 environment."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(searchpath="."),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


JINJA_ENV = create_jinja_env()


def render_template_string(
    template_str: Optional[str], template_variables: dict[str, Any], template_name: str
) -> Optional[str]:
    """
    Renders a Jinja2 template string with the given variables.
    Returns the rendered string, or None if template_str is None.

    Raises:
        TemplateError: If template rendering fails.
    """
    if template_str is None:
        logger.debug(f"Template '{template_name}' is None, skipping rendering.")
        return None

    try:
        template = JINJA_ENV.from_string(str(template_str))
        rendered_text = template.render(template_variables)
        logger.debug(f"Successfully rendered template '{template_name}'.")
        return rendered_text
    except jinja2.exceptions.TemplateError as e:
        error_msg = f"Error rendering '{template_name}' template: {e}"
        if hasattr(e, "lineno") and e.lineno is not None:
            error_msg += f" (near line {e.lineno})"
        raise TemplateError(error_msg) from e
    except Exception as e:
        raise TemplateError(f"An unexpected error occurred during '{template_name}' templating: {e}") from e
