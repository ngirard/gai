"""Configuration management for gai."""

import logging
import pathlib
from typing import Any, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]

from .exceptions import ConfigError

logger = logging.getLogger(__name__)

# Default system instruction template (can be overridden by --conf-system-instruction)
DEFAULT_SYSTEM_INSTRUCTION = None

# Default user instruction template (can be overridden by --conf-user-instruction)
DEFAULT_USER_INSTRUCTION = """<document>
{{ document }}
</document>

{% if input is defined %}
User Query: {{ input }}
{% endif %}
"""

# Default configuration parameters
DEFAULT_CONFIG: dict[str, Any] = {
    "model": "gemini-flash-latest",
    "temperature": 0.1,
    "response-mime-type": "text/plain",
    "max-output-tokens": None,
    "system-instruction": DEFAULT_SYSTEM_INSTRUCTION,
    "user-instruction": DEFAULT_USER_INSTRUCTION,
}

# Schema for configuration parameter types
CONFIG_TYPES: dict[str, type] = {
    "model": str,
    "temperature": float,
    "response-mime-type": str,
    "max-output-tokens": int,
    "system-instruction": str,
    "user-instruction": str,
}

# User-level configuration file path
CONFIG_FILE_DIR = pathlib.Path.home() / ".config" / "gai"
CONFIG_FILE_PATH = CONFIG_FILE_DIR / "config.toml"

# Repository-level configuration relative path
REPO_CONFIG_RELATIVE_PATH = pathlib.Path(".gai") / "config.toml"


def read_file_content(filepath: str) -> str:
    """Reads the content of a file.

    Raises:
        ConfigError: If file is not found or cannot be read.
    """
    try:
        abs_filepath = pathlib.Path(filepath).resolve()
        logger.debug(f"Attempting to read file: {abs_filepath}")
        content = abs_filepath.read_text(encoding="utf-8")
        logger.debug(f"Successfully read file: {abs_filepath}")
        return content
    except FileNotFoundError as e:
        raise ConfigError(f"File not found at '{filepath}' (resolved to '{abs_filepath}')") from e
    except Exception as e:
        raise ConfigError(f"Error reading file '{filepath}' (resolved to '{abs_filepath}'): {e}") from e


def load_config_from_file(filepath: pathlib.Path) -> dict[str, Any]:
    """Loads configuration from a TOML file.

    Raises:
        ConfigError: If TOML is invalid or file cannot be read.
    """
    config: dict[str, Any] = {}
    if filepath.exists():
        logger.info(f"Loading configuration from {filepath}")
        try:
            with open(filepath, "rb") as f:
                config = tomllib.load(f)
            logger.debug(f"Config loaded from file: {config}")
        except tomllib.TOMLDecodeError as e:
            import sys

            # Print clear error to stderr for better user experience
            print(f"Error: Invalid TOML in configuration file {filepath}", file=sys.stderr)
            print(f"  {e}", file=sys.stderr)
            raise ConfigError(f"Invalid TOML in {filepath}: {e}") from e
        except Exception as e:
            import sys

            print(f"Error: Cannot read configuration file {filepath}: {e}", file=sys.stderr)
            raise ConfigError(f"Error reading config file {filepath}: {e}") from e
    else:
        logger.info(f"Configuration file not found at {filepath}. Using defaults and/or CLI args.")
    return config


def find_git_repo_root(start_path: Optional[pathlib.Path] = None) -> Optional[pathlib.Path]:
    """Find the root directory of the current Git repository, if any."""

    current = (start_path or pathlib.Path.cwd()).resolve()

    for candidate in [current, *current.parents]:
        git_marker = candidate / ".git"
        if git_marker.exists():
            return candidate

    return None


def get_repo_config_path(start_path: Optional[pathlib.Path] = None) -> Optional[pathlib.Path]:
    """Return the repository-level configuration path if inside a Git repository."""

    repo_root = find_git_repo_root(start_path)
    if repo_root is None:
        return None

    return repo_root / REPO_CONFIG_RELATIVE_PATH


def _convert_config_values(
    config_data: dict[str, Any], types_schema: dict[str, type], source_name: str, *, warn_unknown: bool = False
) -> dict[str, Any]:
    """
    Converts values in config_data to types specified in types_schema.
    Handles None values appropriately.
    Returns the converted dictionary.

    Args:
        config_data: Dictionary of configuration values
        types_schema: Dictionary mapping config names to expected types
        source_name: Name of the source for error messages
        warn_unknown: If True, warn about keys not in types_schema

    Raises:
        ConfigError: If type conversion fails.
    """
    converted_config: dict[str, Any] = {}
    for name, value in config_data.items():
        if name not in types_schema:
            if warn_unknown:
                logger.warning(
                    f"Unknown configuration parameter '{name}' from {source_name}. "
                    f"This may be a typo. Known parameters: {', '.join(sorted(types_schema.keys()))}"
                )
            converted_config[name] = value
            logger.debug(f"Config parameter '{name}' from {source_name} has no defined type, using as is.")
            continue

        expected_type = types_schema[name]

        if value is None:
            converted_config[name] = None
            continue

        if isinstance(value, expected_type):
            if expected_type == float and isinstance(value, int):
                converted_config[name] = float(value)
            else:
                converted_config[name] = value
            continue

        original_value_for_error = value
        try:
            if expected_type == bool:
                if isinstance(value, str):
                    if value.lower() in ["true", "yes", "1", "on"]:
                        converted_value = True
                    elif value.lower() in ["false", "no", "0", "off"]:
                        converted_value = False
                    else:
                        raise ValueError(f"Boolean value expected (true/false/yes/no/1/0), got '{value}'")
                elif isinstance(value, (int, float)) and value in [0, 1]:
                    converted_value = bool(value)
                else:
                    raise ValueError(f"Cannot convert type {type(value).__name__} to bool for '{name}'")
            else:
                converted_value = expected_type(value)

            converted_config[name] = converted_value

        except (ValueError, TypeError) as e:
            error_msg = (
                f"Error converting config parameter '{name}' from {source_name}: "
                f"Expected {expected_type.__name__}, got '{original_value_for_error}' "
                f"(type: {type(original_value_for_error).__name__}). Original error: {e}"
            )
            raise ConfigError(error_msg) from e

    return converted_config


def _resolve_config_file_paths(config_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Checks specific configuration values (like instruction templates) and,
    if they are strings starting with `@:`, loads their content from the specified file.
    Modifies the dictionary in place.
    """
    resolved_config = config_dict
    template_keys_to_resolve = ["system-instruction", "user-instruction"]

    for key in template_keys_to_resolve:
        value = resolved_config.get(key)
        if isinstance(value, str):
            filepath = None
            if value.startswith("@:"):
                filepath = value[2:]

            if filepath:
                logger.info(f"Attempting to load template for '{key}' from file: '{filepath}'")
                resolved_config[key] = read_file_content(filepath)
                logger.info(f"Successfully loaded template for '{key}' from file: {filepath}")

    return resolved_config


def load_effective_config(args: list[str]) -> dict[str, Any]:
    """
    Loads configuration from defaults, user file, repository file, and CLI --conf- arguments.
    Returns the final merged configuration dictionary.

    Raises:
        ConfigError: If configuration loading or parsing fails.
    """
    # 1. Start with script defaults
    final_config = DEFAULT_CONFIG.copy()
    logger.debug(f"Initial config from defaults: {final_config}")

    # 2. Load and merge config from user config file
    try:
        raw_file_config = load_config_from_file(CONFIG_FILE_PATH)
        if raw_file_config:
            # Warn about unknown keys in config file to help catch typos
            typed_file_config = _convert_config_values(raw_file_config, CONFIG_TYPES, "file", warn_unknown=True)
            resolved_file_config = _resolve_config_file_paths(typed_file_config)
            final_config.update(resolved_file_config)
            logger.debug(f"Config after merging file settings: {final_config}")
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Error decoding TOML from {CONFIG_FILE_PATH}: {e}") from e
    except ConfigError:
        raise

    # 3. Load and merge repository-level config if available
    repo_config_path = get_repo_config_path()
    if repo_config_path is not None:
        try:
            raw_repo_config = load_config_from_file(repo_config_path)
            if raw_repo_config:
                typed_repo_config = _convert_config_values(
                    raw_repo_config, CONFIG_TYPES, "repository", warn_unknown=True
                )
                resolved_repo_config = _resolve_config_file_paths(typed_repo_config)
                final_config.update(resolved_repo_config)
                logger.debug(f"Config after merging repository settings: {final_config}")
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"Error decoding TOML from {repo_config_path}: {e}") from e
        except ConfigError:
            raise

    # 4. Extract and merge CLI configurations (--conf- args only)
    cli_raw_conf_params: dict[str, str] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--conf-"):
            if i + 1 >= len(args):
                raise ConfigError(f"Configuration argument '{arg}' requires a value.")
            conf_name = arg[len("--conf-") :]
            if not conf_name:
                raise ConfigError(f"Configuration argument '{arg}' is missing a name after '--conf-'.")
            cli_raw_conf_params[conf_name] = args[i + 1]
            logger.debug(f"Parsed raw CLI config: {conf_name}={cli_raw_conf_params[conf_name]}")
            i += 2
        else:
            i += 1

    if cli_raw_conf_params:
        typed_cli_config = _convert_config_values(cli_raw_conf_params, CONFIG_TYPES, "CLI")
        resolved_cli_config = _resolve_config_file_paths(typed_cli_config)
        final_config.update(resolved_cli_config)
        logger.debug(f"Config after merging CLI settings: {final_config}")

    logger.info(f"Effective Configuration: {final_config}")
    return final_config
