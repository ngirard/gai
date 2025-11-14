"""Command-line interface for gai."""

import argparse
import logging
import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any, Optional

from .config import CONFIG_FILE_DIR, CONFIG_FILE_PATH, CONFIG_TYPES, DEFAULT_CONFIG, read_file_content
from .exceptions import CliUsageError
from .templates import render_template_string

logger = logging.getLogger(__name__)


def usage(config: dict[str, Any]) -> None:
    """Prints dynamic usage information including config and template parameters."""
    script_name = os.path.basename(sys.argv[0])

    print(f"Usage: {script_name} [options] [--conf-param value ...] [--template-var value ...]")
    print("\nOptions:")
    print("  -h, --help            Show this help message and exit")
    print("  --debug               Enable debug logging output")
    print("  --generate-config     Generate a default config file (TOML) to stdout and exit")
    print("  --show-prompt         Render and print the final templated prompt to stdout and exit")

    print("\nConfiguration:")
    print("  Configuration is loaded in the following order of precedence (later overrides earlier):")
    print("  1. Script defaults.")
    print(f"  2. Configuration file (TOML format): {CONFIG_FILE_PATH}")
    print("  3. Command-line arguments (--conf-<name> value).")
    print("  For string parameters like 'system-instruction' or 'user-instruction',")
    print("  a value starting with `@:` will be interpreted as a file path.")

    print("\nConfiguration Parameters (--conf-<name> value):")
    for name, default_value in DEFAULT_CONFIG.items():
        param_type = CONFIG_TYPES.get(name, type(default_value))
        type_name = param_type.__name__ if param_type else "Any"
        effective_value = config.get(name, default_value)
        display_value = str(effective_value)
        if len(display_value) > 50:
            display_value = display_value[:47] + "..."
        display_value_repr = repr(display_value).replace("{", "{{").replace("}", "}}")
        print(f"  --conf-{name:<20} (type: {type_name}, default: {display_value_repr})")

    print("\nTemplate Variables (--<name> value or --<name> @:path/to/file):")
    print("  These variables are passed as context to the Jinja2 prompt templates.")
    print("  Use --<name> @:path/to/file to load variable content from a file.")
    print("  Paths can be absolute or relative.")

    print("\nExamples:")
    print(f'  {script_name} --document "Summary..." --input "What are the key findings?"')
    print(f"  {script_name} --document @:./report.txt --conf-temperature 0.8")
    print(f'  {script_name} --show-prompt --document @:./doc.txt --topic "AI"')

    print("\nNote: Ensure GOOGLE_API_KEY environment variable is set.")


def pair_args(args: list[str]) -> Generator[tuple[str, str], None, None]:
    """Generator that yields (name_arg, value_arg) pairs from arguments.

    Raises:
        CliUsageError: If argument parsing fails.
    """
    i = 0
    while i < len(args):
        name_arg = args[i]
        if not name_arg.startswith("--"):
            raise CliUsageError(f"Internal Error: Non '--' argument passed to pair_args: '{name_arg}'")

        if i + 1 >= len(args):
            raise CliUsageError(f"Argument '{name_arg}' requires a value.")

        value_arg = args[i + 1]
        yield (name_arg, value_arg)
        i += 2


def process_template_values(
    arg_pairs: Generator[tuple[str, str], None, None],
) -> Generator[tuple[str, str], None, None]:
    """Generator that processes template values, handling @: for file paths."""
    for name_arg, value_arg in arg_pairs:
        name = name_arg[2:]
        if value_arg.startswith("@:"):
            filepath = value_arg[2:]
            processed_value = read_file_content(filepath)
        else:
            processed_value = value_arg
        yield (name, processed_value)


def parse_template_args(args: list[str]) -> dict[str, str]:
    """Parses command-line arguments that are NOT --conf- or known flags.

    Raises:
        CliUsageError: If argument parsing fails.
    """
    template_args_list: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--conf-"):
            i += 2
        elif arg in ["--debug", "-h", "--help", "--generate-config", "--show-prompt"]:
            i += 1
        elif arg.startswith("--"):
            if i + 1 >= len(args):
                raise CliUsageError(f"Template argument '{arg}' requires a value.")
            template_args_list.append(arg)
            template_args_list.append(args[i + 1])
            logger.debug(f"Identified template arg: {arg} {args[i + 1]}")
            i += 2
        else:
            raise CliUsageError(f"Unexpected argument '{arg}'. Arguments must start with '--'.")

    arg_pairs_generator = pair_args(template_args_list)
    processed_pairs_generator = process_template_values(arg_pairs_generator)
    template_variables = dict(processed_pairs_generator)
    logger.debug(f"Template Variables: {template_variables}")
    return template_variables


def show_rendered_prompt(
    config: dict[str, Any], template_variables: dict[str, str], part: Optional[str] = None
) -> None:
    """Renders and prints the system and user instruction templates.

    Args:
        config: Configuration dictionary
        template_variables: Template variables
        part: Optional part to render ('system', 'user', or None for both)
    """
    logger.info("Rendering prompt for display...")

    system_instruction_template_str = config.get("system-instruction")
    user_instruction_template_str = config.get("user-instruction")

    if part == "system" or part is None:
        rendered_system_instruction = render_template_string(
            system_instruction_template_str, template_variables, "system-instruction"
        )
        system_content_processed = (rendered_system_instruction or "").strip()
    else:
        system_content_processed = ""

    if part == "user" or part is None:
        rendered_user_instruction = render_template_string(
            user_instruction_template_str, template_variables, "user-instruction"
        )
        user_content_processed = (rendered_user_instruction or "").strip()
    else:
        user_content_processed = ""

    # Output based on what was requested
    if part == "system":
        print(system_content_processed)
    elif part == "user":
        print(user_content_processed)
    else:
        # Both parts
        if not system_content_processed:
            final_output = user_content_processed
        else:
            system_block = f"<system_instruction>\n{system_content_processed}\n</system_instruction>"
            user_block = f"<user_instruction>\n{user_content_processed}\n</user_instruction>"
            final_output = f"{system_block}\n{user_block}"
        print(final_output)


def create_parser() -> argparse.ArgumentParser:
    """Creates and returns the main argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="gai",
        description="Google Gemini prompting tool with flexible CLI, templating, and configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument("--debug", action="store_true", help="Enable debug logging output")

    # Create subparsers
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ===== GENERATE SUBCOMMAND =====
    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate content using Gemini AI (default action)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    generate_parser.add_argument(
        "--show-prompt", action="store_true", help="Display the rendered prompt instead of generating"
    )
    _add_config_and_template_args(generate_parser)

    # ===== CONFIG SUBCOMMAND =====
    config_parser = subparsers.add_parser(
        "config",
        help="Manage configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command", help="Config commands")

    # config view
    config_subparsers.add_parser("view", help="Show the effective configuration")

    # config edit
    config_subparsers.add_parser("edit", help="Open configuration file in $EDITOR")

    # config validate
    validate_parser = config_subparsers.add_parser("validate", help="Validate configuration file")
    validate_parser.add_argument("--file", type=str, help="Path to config file (default: ~/.config/gai/config.toml)")

    # config defaults
    config_subparsers.add_parser("defaults", help="Print default configuration to stdout")

    # config path
    config_subparsers.add_parser("path", help="Show the configuration file path")

    # ===== TEMPLATE SUBCOMMAND =====
    template_parser = subparsers.add_parser(
        "template",
        help="Work with prompt templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    template_subparsers = template_parser.add_subparsers(dest="template_command", help="Template commands")

    # template render
    render_parser = template_subparsers.add_parser(
        "render",
        help="Render prompt template with variables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Add a flag to specify which part to render
    render_parser.add_argument(
        "--part",
        choices=["both", "user", "system"],
        default="both",
        help="Which part to render (default: both)",
    )

    # Add config and template args to render_parser
    _add_config_and_template_args(render_parser)

    return parser


def _add_config_and_template_args(parser: argparse.ArgumentParser) -> None:
    """Add config and template arguments to a parser."""
    # Config arguments
    config_group = parser.add_argument_group("configuration options")
    for name, default_value in DEFAULT_CONFIG.items():
        param_type = CONFIG_TYPES.get(name, type(default_value))
        type_name = param_type.__name__ if param_type else "Any"
        config_group.add_argument(
            f"--conf-{name}",
            type=str,  # We'll convert later
            metavar="VALUE",
            help=f"Set {name} (type: {type_name})",
        )

    # Note: Template variables are handled separately via parse_known_args
    # They are in the form --name value and will be in the "remaining" args


def parse_args_for_new_cli(args: list[str]) -> tuple[argparse.Namespace, dict[str, str]]:
    """Parse arguments using the new CLI structure.

    Returns:
        Tuple of (parsed_args, template_variables)
    """
    parser = create_parser()

    # First pass: parse known args to get command structure and config
    parsed, remaining = parser.parse_known_args(args)

    # Parse template variables from remaining args
    template_vars = parse_template_args_from_list(remaining)

    return parsed, template_vars


def parse_template_args_from_list(args: list[str]) -> dict[str, str]:
    """Parse template variables from a list of arguments.

    Template variables are in the form --name value.
    """
    template_vars: dict[str, str] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            if i + 1 < len(args):
                name = arg[2:]
                value = args[i + 1]

                # Handle @: file references
                if value.startswith("@:"):
                    filepath = value[2:]
                    template_vars[name] = read_file_content(filepath)
                else:
                    template_vars[name] = value
                i += 2
            else:
                raise CliUsageError(f"Template argument '{arg}' requires a value.")
        else:
            raise CliUsageError(f"Unexpected argument '{arg}'. Template variables must start with '--'.")

    return template_vars


# ===== Config subcommand handlers =====


def handle_config_view(config: dict[str, Any]) -> None:
    """Display the effective configuration."""
    import json

    print("Effective Configuration:")
    print(json.dumps(config, indent=2, default=str))


def handle_config_edit() -> None:
    """Open the configuration file in $EDITOR."""
    editor = os.environ.get("EDITOR", "vi")

    # Ensure config directory exists
    CONFIG_FILE_DIR.mkdir(parents=True, exist_ok=True)

    # Create file if it doesn't exist
    if not CONFIG_FILE_PATH.exists():
        CONFIG_FILE_PATH.write_text("# gai configuration file\n")

    # Open in editor
    try:
        subprocess.run([editor, str(CONFIG_FILE_PATH)], check=True)  # noqa: S603
    except subprocess.CalledProcessError as e:
        logger.error(f"Editor exited with error code {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        logger.error(f"Editor '{editor}' not found. Set EDITOR environment variable.")
        sys.exit(1)


def handle_config_validate(file_path: Optional[str] = None) -> None:
    """Validate the configuration file."""
    from .config import load_config_from_file

    config_path = Path(file_path) if file_path else CONFIG_FILE_PATH

    if not config_path.exists():
        print(f"Configuration file not found: {config_path}")
        sys.exit(1)

    try:
        config = load_config_from_file(config_path)
        print(f"✓ Configuration file is valid: {config_path}")
        print(f"  Loaded {len(config)} configuration parameters")
    except Exception as e:
        print(f"✗ Configuration file is invalid: {config_path}")
        print(f"  Error: {e}")
        sys.exit(1)


def handle_config_defaults() -> None:
    """Print default configuration to stdout."""
    import tomli_w

    # Filter out None values for TOML serialization
    config_to_dump = {k: v for k, v in DEFAULT_CONFIG.items() if v is not None}

    print("# Default configuration for gai")
    print(f"# Save this to: {CONFIG_FILE_PATH}")
    print()
    print(tomli_w.dumps(config_to_dump))


def handle_config_path() -> None:
    """Show the configuration file path."""
    print(f"Configuration file path: {CONFIG_FILE_PATH}")
    if CONFIG_FILE_PATH.exists():
        print("Status: exists")
    else:
        print("Status: not found")
