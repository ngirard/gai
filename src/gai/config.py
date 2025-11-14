"""Configuration management for gai."""

import logging
import pathlib
import sys
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

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
    "enable-feature-x": False,
    "system-instruction": DEFAULT_SYSTEM_INSTRUCTION,
    "user-instruction": DEFAULT_USER_INSTRUCTION,
}

# Schema for configuration parameter types
CONFIG_TYPES: dict[str, type] = {
    "model": str,
    "temperature": float,
    "response-mime-type": str,
    "max-output-tokens": int,
    "enable-feature-x": bool,
    "system-instruction": str,
    "user-instruction": str,
}

# Configuration file path
CONFIG_FILE_DIR = pathlib.Path.home() / ".config" / "gai"
CONFIG_FILE_PATH = CONFIG_FILE_DIR / "config.toml"


def read_file_content(filepath: str) -> str:
    """Reads the content of a file."""
    try:
        abs_filepath = pathlib.Path(filepath).resolve()
        logger.debug(f"Attempting to read file: {abs_filepath}")
        content = abs_filepath.read_text(encoding="utf-8")
        logger.debug(f"Successfully read file: {abs_filepath}")
        return content
    except FileNotFoundError:
        logger.error(f"File not found at '{filepath}' (resolved to '{abs_filepath}')")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading file '{filepath}' (resolved to '{abs_filepath}'): {e}")
        sys.exit(1)


def load_config_from_file(filepath: pathlib.Path) -> dict[str, Any]:
    """Loads configuration from a TOML file."""
    config: dict[str, Any] = {}
    if filepath.exists():
        logger.info(f"Loading configuration from {filepath}")
        try:
            with open(filepath, "rb") as f:
                config = tomllib.load(f)
            logger.debug(f"Config loaded from file: {config}")
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML from {filepath}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reading config file {filepath}: {e}")
            raise
    else:
        logger.info(f"Configuration file not found at {filepath}. Using defaults and/or CLI args.")
    return config


def _convert_config_values(
    config_data: dict[str, Any], types_schema: dict[str, type], source_name: str
) -> dict[str, Any]:
    """
    Converts values in config_data to types specified in types_schema.
    Handles None values appropriately.
    Returns the converted dictionary. Raises ValueError or TypeError on failure.
    """
    converted_config: dict[str, Any] = {}
    for name, value in config_data.items():
        if name not in types_schema:
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
            raise type(e)(
                f"Error converting config parameter '{name}' from {source_name}: "
                f"Expected {expected_type.__name__}, got '{original_value_for_error}' "
                f"(type: {type(original_value_for_error).__name__}). Original error: {e}"
            ) from e

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
    Loads configuration from defaults, file, and CLI --conf- arguments.
    Returns the final merged configuration dictionary.
    """
    # 1. Start with script defaults
    final_config = DEFAULT_CONFIG.copy()
    logger.debug(f"Initial config from defaults: {final_config}")

    # 2. Load and merge config from file
    try:
        raw_file_config = load_config_from_file(CONFIG_FILE_PATH)
        if raw_file_config:
            typed_file_config = _convert_config_values(raw_file_config, CONFIG_TYPES, "file")
            resolved_file_config = _resolve_config_file_paths(typed_file_config)
            final_config.update(resolved_file_config)
            logger.debug(f"Config after merging file settings: {final_config}")
    except (tomllib.TOMLDecodeError, ValueError, TypeError):
        sys.exit(1)

    # 3. Extract and merge CLI configurations (--conf- args only)
    cli_raw_conf_params: dict[str, str] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--conf-"):
            if i + 1 >= len(args):
                logger.error(f"Error: Configuration argument '{arg}' requires a value.")
                sys.exit(1)
            conf_name = arg[len("--conf-") :]
            if not conf_name:
                logger.error(f"Error: Configuration argument '{arg}' is missing a name after '--conf-'.")
                sys.exit(1)
            cli_raw_conf_params[conf_name] = args[i + 1]
            logger.debug(f"Parsed raw CLI config: {conf_name}={cli_raw_conf_params[conf_name]}")
            i += 2
        else:
            i += 1

    if cli_raw_conf_params:
        try:
            typed_cli_config = _convert_config_values(cli_raw_conf_params, CONFIG_TYPES, "CLI")
            resolved_cli_config = _resolve_config_file_paths(typed_cli_config)
            final_config.update(resolved_cli_config)
            logger.debug(f"Config after merging CLI settings: {final_config}")
        except (ValueError, TypeError):
            sys.exit(1)

    logger.info(f"Effective Configuration: {final_config}")
    return final_config
