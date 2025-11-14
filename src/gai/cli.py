"""Command-line interface for gai."""

import logging
import os
import sys
from collections.abc import Generator
from typing import Any

from .config import CONFIG_FILE_PATH, CONFIG_TYPES, DEFAULT_CONFIG, read_file_content
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


def show_rendered_prompt(config: dict[str, Any], template_variables: dict[str, str]) -> None:
    """Renders and prints the system and user instruction templates."""
    logger.info("Rendering prompt for display (--show-prompt)...")

    system_instruction_template_str = config.get("system-instruction")
    user_instruction_template_str = config.get("user-instruction")

    rendered_system_instruction = render_template_string(
        system_instruction_template_str, template_variables, "system-instruction (for --show-prompt)"
    )

    rendered_user_instruction = render_template_string(
        user_instruction_template_str, template_variables, "user-instruction (for --show-prompt)"
    )

    system_content_processed = (rendered_system_instruction or "").strip()
    user_content_processed = (rendered_user_instruction or "").strip()

    if not system_content_processed:
        final_output = user_content_processed
    else:
        system_block = f"<system_instruction>\n{system_content_processed}\n</system_instruction>"
        user_block = f"<user_instruction>\n{user_content_processed}\n</user_instruction>"
        final_output = f"{system_block}\n{user_block}"

    print(final_output)
