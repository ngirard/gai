"""Template handling for gai using Jinja2.

This module provides template rendering functionality with support for:
- Catalog-based template resolution using logical names
- Named templates with tier-based precedence
- Recursive template composition via extends/include/import
- Strict variable checking and clear error messages

Named templates support full recursive composition: templates can extend, include,
or import other templates to any depth, and all templates share the same variable
context and catalog-based resolver.
"""

import logging
from typing import Any, Optional

import jinja2

from .exceptions import TemplateAmbiguityError, TemplateError, TemplateNotFoundError
from .template_catalog import DEFAULT_TEMPLATE_EXTENSIONS, TIER_PRECEDENCE, TemplateRecord

logger = logging.getLogger(__name__)


def create_jinja_env() -> jinja2.Environment:
    """Creates and configures the global Jinja2 environment.

    Note: FileSystemLoader is configured but currently unused, as all templates
    are rendered via from_string(). This loader could be used in the future to
    support named template files (e.g., loading from ~/.config/gai/templates/).
    """
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


def resolve_template_name(
    catalog: list[TemplateRecord],
    logical_name: str,
    allowed_extensions: tuple[str, ...] = DEFAULT_TEMPLATE_EXTENSIONS,
) -> TemplateRecord:
    """Resolve a logical template name to a specific template record.

    This function implements the tier-aware resolution algorithm from the specification:
    - Handles explicit extensions (.j2, .j2.md) vs extensionless names
    - Distinguishes path-specific names (containing /) from basename-only names
    - Processes tiers in precedence order (project, user, builtin)
    - Returns the unique match from the first tier with candidates
    - Raises TemplateAmbiguityError if multiple matches exist in a tier
    - Raises TemplateNotFoundError if no matches found in any tier

    Args:
        catalog: List of TemplateRecord objects to search
        logical_name: The logical name to resolve (e.g., "summary" or "layout/base.j2")
        allowed_extensions: Tuple of recognized template extensions

    Returns:
        The unique TemplateRecord matching the logical name

    Raises:
        TemplateNotFoundError: If no template matches the logical name
        TemplateAmbiguityError: If multiple templates match in the same tier
    """
    # Step 1: Check if the name includes an explicit extension
    required_extension: Optional[str] = None
    base_name = logical_name

    for ext in allowed_extensions:
        if logical_name.endswith(ext):
            required_extension = ext
            base_name = logical_name[: -len(ext)]
            break

    logger.debug(
        f"Resolving template name: '{logical_name}' -> base_name='{base_name}', required_extension={required_extension}"
    )

    # Step 2: Determine if this is a path-specific or basename-only name
    is_path_specific = "/" in base_name

    # Step 3: Group catalog by tier
    records_by_tier: dict[str, list[TemplateRecord]] = {}
    searched_roots: set[str] = set()

    for record in catalog:
        tier = record.tier
        if tier not in records_by_tier:
            records_by_tier[tier] = []
        records_by_tier[tier].append(record)
        searched_roots.add(str(record.absolute_path.parent))

    # Step 4: Process tiers in precedence order
    tier_order = sorted(TIER_PRECEDENCE.keys(), key=lambda t: TIER_PRECEDENCE[t])

    for tier in tier_order:
        tier_records = records_by_tier.get(tier, [])
        if not tier_records:
            continue

        # Step 5: Find candidates in this tier
        tier_candidates: list[TemplateRecord] = []

        for record in tier_records:
            # Check logical name match
            if is_path_specific:
                # Path-specific: exact match required
                if record.logical_name_full != base_name:
                    continue
            else:
                # Basename-only: match last path segment
                record_basename = record.logical_name_full.split("/")[-1]
                if record_basename != base_name:
                    continue

            # Check extension match
            if required_extension is not None and record.extension != required_extension:
                continue

            tier_candidates.append(record)

        # Step 6: Handle candidates for this tier
        if len(tier_candidates) == 0:
            # No matches in this tier, continue to next tier
            continue
        if len(tier_candidates) == 1:
            # Exactly one match - success!
            logger.debug(f"Resolved '{logical_name}' to {tier_candidates[0].absolute_path}")
            return tier_candidates[0]

        # Multiple matches - ambiguity error
        candidates_info = [(str(r.relative_path), r.extension) for r in tier_candidates]
        raise TemplateAmbiguityError(logical_name, tier, candidates_info)

    # Step 7: No tier had any candidates
    raise TemplateNotFoundError(logical_name, sorted(searched_roots))


class CatalogLoader(jinja2.BaseLoader):
    """Jinja2 loader that resolves template names using the template catalog.

    This loader implements Jinja2's BaseLoader interface and uses the catalog-based
    resolution system to support Obsidian-style extensionless template names in
    {% extends %}, {% include %}, and {% import %} statements.

    The loader enables recursive template composition: when a template includes or
    extends another template, the same catalog and resolution rules are used for
    all nested references, allowing templates to be composed to any depth.

    The loader:
    - Calls resolve_template_name() to map logical names to template files
    - Reads template content from the resolved absolute path
    - Provides proper mtime checking for Jinja's auto-reload feature
    """

    def __init__(
        self, catalog: list[TemplateRecord], allowed_extensions: tuple[str, ...] = DEFAULT_TEMPLATE_EXTENSIONS
    ):
        """Initialize the loader with a template catalog.

        Args:
            catalog: List of TemplateRecord objects to use for resolution
            allowed_extensions: Tuple of recognized template extensions
        """
        self._catalog = catalog
        self._allowed_extensions = allowed_extensions
        logger.debug(f"CatalogLoader initialized with {len(catalog)} templates")

    def get_source(self, _environment: jinja2.Environment, template: str) -> tuple[str, Optional[str], Optional[Any]]:
        """Load a template by its logical name.

        This method is called by Jinja2 when resolving template names in
        {% extends %}, {% include %}, and {% import %} statements.

        Args:
            environment: The Jinja2 environment requesting the template
            template: The logical template name to resolve

        Returns:
            A tuple of (source, filename, uptodate_function) where:
            - source: The template content as a string
            - filename: The absolute path to the template file (for error messages)
            - uptodate_function: A callable that returns True if the template is still current

        Raises:
            jinja2.TemplateNotFound: If the template cannot be resolved or read
        """
        try:
            # Resolve the logical name to a template record
            record = resolve_template_name(self._catalog, template, self._allowed_extensions)
            absolute_path = record.absolute_path

            # Read the template content
            try:
                source = absolute_path.read_text(encoding="utf-8")
            except Exception as e:
                raise jinja2.TemplateNotFound(template, message=f"Error reading template file: {e}") from e

            # Get file modification time for caching
            try:
                mtime = absolute_path.stat().st_mtime
            except Exception:
                mtime = None

            # Create uptodate function that checks if file hasn't been modified
            def uptodate() -> bool:
                if mtime is None:
                    return False
                try:
                    return absolute_path.stat().st_mtime == mtime
                except Exception:
                    return False

            logger.debug(f"Loaded template '{template}' from {absolute_path}")
            return source, str(absolute_path), uptodate

        except TemplateNotFoundError as e:
            # Convert to Jinja2's TemplateNotFound exception
            raise jinja2.TemplateNotFound(template, message=str(e)) from e
        except TemplateAmbiguityError as e:
            # Convert to TemplateNotFound with the ambiguity message
            # (Jinja2 doesn't have a built-in ambiguity exception type)
            raise jinja2.TemplateNotFound(template, message=str(e)) from e
        except Exception as e:
            raise jinja2.TemplateNotFound(template, message=f"Unexpected error: {e}") from e


def create_jinja_env_from_catalog(
    catalog: list[TemplateRecord],
    allowed_extensions: tuple[str, ...] = DEFAULT_TEMPLATE_EXTENSIONS,
) -> jinja2.Environment:
    """Create a Jinja2 environment that uses catalog-based template resolution.

    This function creates an environment with:
    - CatalogLoader for resolving extensionless logical names
    - StrictUndefined to catch missing variables
    - Block trimming for cleaner output

    The environment supports recursive template composition: templates loaded
    through this environment can extend, include, or import other templates
    using logical names, and all such references will be resolved through the
    same catalog using consistent tier precedence rules.

    Args:
        catalog: List of TemplateRecord objects for template resolution
        allowed_extensions: Tuple of recognized template extensions

    Returns:
        A configured Jinja2 Environment
    """
    env = jinja2.Environment(
        loader=CatalogLoader(catalog, allowed_extensions),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    logger.debug("Created Jinja2 environment with CatalogLoader")
    return env


def render_system_instruction(config: dict[str, Any], template_vars: dict[str, Any]) -> Optional[str]:
    """Render the system instruction using either named templates or literal strings.

    This function implements the precedence rule for system instructions:
    1. If 'system-instruction-template' is set, use catalog-based rendering
    2. Otherwise, fall back to 'system-instruction' with render_template_string

    Named templates support recursive composition: if a named template extends or
    includes other templates, those nested templates are resolved using the same
    catalog and variable context.

    Args:
        config: Configuration dictionary
        template_vars: Template variables for rendering

    Returns:
        Rendered system instruction string, or None if no instruction is configured

    Raises:
        TemplateError: If template rendering fails
        TemplateNotFoundError: If a named template cannot be found
        TemplateAmbiguityError: If a named template is ambiguous
    """
    # Check for named template first (higher precedence)
    template_name = config.get("system-instruction-template")
    if template_name:
        logger.debug(f"Using named template for system instruction: '{template_name}'")
        # Import here to avoid circular dependency
        from .config import get_template_roots
        from .template_catalog import discover_templates

        # Build catalog from configured roots
        roots = get_template_roots(config)
        catalog = discover_templates(roots["project"], roots["user"], roots["builtin"])

        # Create environment with catalog loader
        env = create_jinja_env_from_catalog(catalog)

        try:
            # Load and render the named template
            template = env.get_template(template_name)
            rendered = template.render(template_vars)
            logger.debug(f"Successfully rendered system instruction from template '{template_name}'")
            return rendered
        except jinja2.TemplateNotFound as e:
            raise TemplateNotFoundError(template_name, []) from e
        except jinja2.exceptions.TemplateError as e:
            raise TemplateError(f"Error rendering system instruction template '{template_name}': {e}") from e

    # Fall back to literal template string
    literal_template = config.get("system-instruction")
    return render_template_string(literal_template, template_vars, "system-instruction")


def render_user_instruction(config: dict[str, Any], template_vars: dict[str, Any]) -> Optional[str]:
    """Render the user instruction using either named templates or literal strings.

    This function implements the precedence rule for user instructions:
    1. If 'user-instruction-template' is set, use catalog-based rendering
    2. Otherwise, fall back to 'user-instruction' with render_template_string

    Named templates support recursive composition: if a named template extends or
    includes other templates, those nested templates are resolved using the same
    catalog and variable context.

    Args:
        config: Configuration dictionary
        template_vars: Template variables for rendering

    Returns:
        Rendered user instruction string, or None if no instruction is configured

    Raises:
        TemplateError: If template rendering fails
        TemplateNotFoundError: If a named template cannot be found
        TemplateAmbiguityError: If a named template is ambiguous
    """
    # Check for named template first (higher precedence)
    template_name = config.get("user-instruction-template")
    if template_name:
        logger.debug(f"Using named template for user instruction: '{template_name}'")
        # Import here to avoid circular dependency
        from .config import get_template_roots
        from .template_catalog import discover_templates

        # Build catalog from configured roots
        roots = get_template_roots(config)
        catalog = discover_templates(roots["project"], roots["user"], roots["builtin"])

        # Create environment with catalog loader
        env = create_jinja_env_from_catalog(catalog)

        try:
            # Load and render the named template
            template = env.get_template(template_name)
            rendered = template.render(template_vars)
            logger.debug(f"Successfully rendered user instruction from template '{template_name}'")
            return rendered
        except jinja2.TemplateNotFound as e:
            raise TemplateNotFoundError(template_name, []) from e
        except jinja2.exceptions.TemplateError as e:
            raise TemplateError(f"Error rendering user instruction template '{template_name}': {e}") from e

    # Fall back to literal template string
    literal_template = config.get("user-instruction")
    return render_template_string(literal_template, template_vars, "user-instruction")
