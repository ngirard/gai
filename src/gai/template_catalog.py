"""Template catalog and discovery for gai.

This module implements the template discovery and catalog system as specified
in goals/templates/Specification.md. It provides:

- Data structures for template records and tiers
- Discovery algorithm to scan template roots
- Catalog ordering by tier precedence, root order, and path

The catalog system underpins recursive template resolution: when templates use
{% extends %}, {% include %}, or {% import %} to reference other templates,
the CatalogLoader in templates.py uses this catalog to resolve all nested
references using consistent tier precedence rules.
"""

import logging
import pathlib
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# Tier types with fixed precedence order: project > user > builtin
TierType = Literal["project", "user", "builtin"]

# Recognized template file extensions
DEFAULT_TEMPLATE_EXTENSIONS = (".j2", ".j2.md")

# Tier precedence ordering (lower index = higher precedence)
TIER_PRECEDENCE: dict[TierType, int] = {
    "project": 0,
    "user": 1,
    "builtin": 2,
}


@dataclass
class TemplateRecord:
    """Represents a discovered template file with metadata.

    Attributes:
        logical_name_full: Canonical logical name without extension (e.g., "layout/base_conversation")
        relative_path: Path relative to its root, including extension (e.g., "layout/base_conversation.j2")
        absolute_path: Absolute filesystem path to the template file
        tier: The tier this template belongs to ("project", "user", or "builtin")
        root_index: Zero-based index of the root within its tier
        extension: File extension including the dot (e.g., ".j2", ".j2.md")
    """

    logical_name_full: str
    relative_path: pathlib.Path
    absolute_path: pathlib.Path
    tier: TierType
    root_index: int
    extension: str

    def __post_init__(self):
        """Validate the template record after initialization."""
        if self.tier not in TIER_PRECEDENCE:
            raise ValueError(f"Invalid tier: {self.tier}")
        if not self.extension.startswith("."):
            raise ValueError(f"Extension must start with '.': {self.extension}")


def discover_templates(
    project_roots: list[pathlib.Path],
    user_roots: list[pathlib.Path],
    builtin_roots: list[pathlib.Path],
    allowed_extensions: tuple[str, ...] = DEFAULT_TEMPLATE_EXTENSIONS,
) -> list[TemplateRecord]:
    """Discover template files across all configured roots.

    This function implements the discovery algorithm from the specification:
    - Scans tiers in precedence order (project, user, builtin)
    - Within each tier, scans roots in configuration order
    - Recursively walks each root directory
    - Creates TemplateRecord for each file with a recognized extension
    - Returns records in catalog ordering (tier, root_index, relative_path)

    Args:
        project_roots: List of project-tier template root directories
        user_roots: List of user-tier template root directories
        builtin_roots: List of builtin-tier template root directories
        allowed_extensions: Tuple of allowed file extensions (default: .j2, .j2.md)

    Returns:
        List of TemplateRecord objects, ordered by tier, root_index, then relative_path

    Note:
        Non-existent roots are skipped with a debug log message.
        Non-regular files and files with unrecognized extensions are ignored.
    """
    records: list[TemplateRecord] = []

    # Process tiers in precedence order
    tiers: list[tuple[TierType, list[pathlib.Path]]] = [
        ("project", project_roots),
        ("user", user_roots),
        ("builtin", builtin_roots),
    ]

    for tier_name, roots in tiers:
        for root_index, root_path in enumerate(roots):
            if not root_path.exists():
                logger.debug(f"Template root does not exist, skipping: {root_path}")
                continue

            if not root_path.is_dir():
                logger.warning(f"Template root is not a directory, skipping: {root_path}")
                continue

            logger.debug(f"Scanning template root [{tier_name}:{root_index}]: {root_path}")

            # Recursively walk the directory
            for file_path in sorted(root_path.rglob("*")):
                # Skip non-regular files
                if not file_path.is_file():
                    continue

                # Check if extension is recognized
                extension = _get_template_extension(file_path, allowed_extensions)
                if extension is None:
                    continue

                # Compute relative path from root
                try:
                    relative_path = file_path.relative_to(root_path)
                except ValueError:
                    logger.warning(f"Could not compute relative path for {file_path} from {root_path}")
                    continue

                # Compute logical name by removing extension and normalizing separators
                logical_name_full = _compute_logical_name(relative_path, extension)

                # Create template record
                record = TemplateRecord(
                    logical_name_full=logical_name_full,
                    relative_path=relative_path,
                    absolute_path=file_path,
                    tier=tier_name,
                    root_index=root_index,
                    extension=extension,
                )
                records.append(record)

                logger.debug(f"Discovered template: {logical_name_full} -> {file_path}")

    return records


def _get_template_extension(file_path: pathlib.Path, allowed_extensions: tuple[str, ...]) -> str | None:
    """Determine if a file has a recognized template extension.

    Args:
        file_path: Path to the file
        allowed_extensions: Tuple of allowed extensions

    Returns:
        The matched extension (including dot) or None if not recognized
    """
    file_name = file_path.name

    # Check each allowed extension
    for ext in allowed_extensions:
        if file_name.endswith(ext):
            return ext

    return None


def _compute_logical_name(relative_path: pathlib.Path, extension: str) -> str:
    """Compute the logical name for a template file.

    The logical name is the relative path without the extension, with forward
    slashes as separators (even on Windows).

    Args:
        relative_path: Path relative to the template root
        extension: The file extension (including dot)

    Returns:
        Logical name as a string with forward slashes
    """
    # Convert to string with forward slashes
    path_str = relative_path.as_posix()

    # Remove the extension
    if path_str.endswith(extension):
        path_str = path_str[: -len(extension)]

    return path_str


class TemplateCatalog:
    """A collection of discovered templates with utility methods.

    This class wraps a list of TemplateRecord objects and provides methods
    for querying and filtering the catalog.
    """

    def __init__(self, records: list[TemplateRecord]):
        """Initialize the catalog with template records.

        Args:
            records: List of TemplateRecord objects (should be pre-sorted)
        """
        self.records = records

    def __len__(self) -> int:
        """Return the number of templates in the catalog."""
        return len(self.records)

    def __iter__(self):
        """Iterate over template records in catalog order."""
        return iter(self.records)

    def filter_by_tier(self, tier: TierType) -> list[TemplateRecord]:
        """Filter records by tier.

        Args:
            tier: Tier name to filter by

        Returns:
            List of TemplateRecord objects for the specified tier
        """
        return [r for r in self.records if r.tier == tier]

    def get_all_logical_names(self) -> list[str]:
        """Get all logical names in catalog order.

        Returns:
            List of logical_name_full strings in catalog order
        """
        return [r.logical_name_full for r in self.records]


def build_template_catalog(config: dict[str, any]) -> TemplateCatalog:
    """Build a TemplateCatalog from the effective configuration.

    This is the centralized function for converting configuration into a usable
    template catalog, used by template list, browse, and render commands.

    Steps:
      - Resolve template roots from config
      - Discover templates across project/user/builtin tiers
      - Wrap them in a TemplateCatalog

    Args:
        config: The effective configuration dictionary

    Returns:
        TemplateCatalog containing all discovered templates
    """
    from .config import get_template_roots

    roots = get_template_roots(config)
    records = discover_templates(
        project_roots=roots["project"],
        user_roots=roots["user"],
        builtin_roots=roots["builtin"],
    )
    return TemplateCatalog(records)
