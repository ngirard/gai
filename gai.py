#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "google-genai==1.15.0",
#     "tomli; python_version < '3.11'", # For TOML config file reading
#     "toml", # For generating TOML config file
#     "Jinja2==3.1.6", # Added Jinja2 dependency
# ]
# ///

# ##############################################################################
#
# gai -- GenAI Prompting Script with flexible CLI, templating, and configuration
#
# Rationale:
# This script provides a robust and flexible command-line interface for
# interacting with the Google GenAI API. The primary goal is to move beyond
# static, hardcoded prompts and generation parameters, allowing users to
# dynamically control the model's input and behavior directly from the shell.
#
# Design Decisions:
#
# 1.  Flexible Command-Line Arguments:
# - Problem: Standard `argparse` requires pre-defining every possible
#   argument. We need to support arbitrary key-value pairs for prompt
#   templating.
# - Solution: Parse the command-line arguments manually.
#
# 2.  Prompt Templating (using Jinja2):
# - Problem: Prompt content needs to be dynamic based on user input and
#   potentially include logic (conditionals, loops, filters).
# - Solution: Use Jinja2. This provides a powerful, widely-used templating
#   engine capable of complex logic beyond simple variable substitution.
#   Variables are passed as a context dictionary.
#
# 3.  File Content Loading:
# - Problem: Prompt variables (especially documents) can be large and
#   should be loaded from files rather than passed directly on the command line.
# - Solution: Implement a simple convention where a value prefixed with
#   `@:` is interpreted as a file path, and its content is read into the
#   corresponding variable. This is handled during the argument parsing
#   pipeline.
#
# 4.  Configurable Generation Parameters:
# - Problem: Model, temperature, response format, etc., should be easily
#   adjustable without modifying the code, and persist across sessions.
# - Solution: Introduce a dedicated `--conf-<name> value` syntax for
#   configuration parameters. These are parsed separately from template
#   variables. Default values are defined in `DEFAULT_CONFIG`.
#   Configuration is loaded in layers:
#   1. Script defaults (`DEFAULT_CONFIG`).
#   2. User configuration file (`~/.config/genai_cli/config.toml`).
#   3. Command-line `--conf-` arguments.
#   Later layers override earlier ones.
#   Systematic type conversion (e.g., float for temperature, int for
#   token counts, bool for flags) is applied with error handling.
#   Configuration values themselves can also be loaded from files using `@:`.
#
# 5.  Dynamic Help/Usage Information:
# - Problem: Standard `argparse` help doesn't know about our custom
#   template variables or `--conf-` parameters.
# - Solution: Manually intercept `--help` and generate usage information
#   dynamically. Configuration parameters are listed by inspecting
#   `DEFAULT_CONFIG`. **Note:** Automatic listing of template variables
#   from Jinja2 templates is complex and has been removed. Users must
#   know the variables expected by their templates.
#
# 6.  Structured Logging:
# - Problem: Avoid mixing internal script messages (parsing details, config
#   used) with the actual model output (which goes to stdout).
# - Solution: Utilize Python's standard `logging` module. Informational
#   and debug messages are directed to stderr via logging, while the model's
#   response is printed directly to stdout. A `--debug` flag is added for
#   verbose logging.
#
# 7.  Code Structure and Modularity (SOLID/SRP):
# - Problem: The original `generate` function was monolithic, handling
#   prompt preparation, config setup, API call, and output streaming.
# - Solution: Refactor `generate` into smaller, single-responsibility
#   functions (`prepare_prompt_contents`, `prepare_generate_content_config_dict`,
#   `execute_generation_stream`, `stream_output`). The main `generate`
#   function now acts as an orchestrator. Argument parsing is structured
#   with dedicated functions for config loading and template variable
#   processing. Templating logic is now encapsulated using Jinja2 and a
#   dedicated `render_template_string` helper.
#
# 8.  Show Rendered Prompt:
# - Problem: Users may want to inspect the fully rendered prompt before sending
#   it to the API, especially when debugging complex templates.
# - Solution: Implement a `--show-prompt` CLI option that renders both system
#   and user instructions with the provided template variables, prints them
#   to stdout in a structured format, and exits.
#
# Prerequisites:
# - Python 3.9+
# - Dependencies listed in the `uv run --script` header (`google-genai`, `tomli`, `toml`, `Jinja2`).
# - `GOOGLE_API_KEY` environment variable set (preferred by new SDK).
#
# Usage:
# Run the script with `--help` for dynamic usage details.
# Example: `./your_script_name.py --document "..." --input "..." --conf-temperature 0.8`
# Example (show prompt): `./your_script_name.py --show-prompt --document @:./report.txt --topic "AI"`
#
# ##############################################################################

import os
import sys
import logging
import pathlib
from typing import Generator, Tuple, List, Dict, Any, Set, Optional

# For Python 3.11+ tomllib is standard, for older use tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib # type: ignore

import toml # Import the toml library for writing
import jinja2

from google import genai
from google.genai import types

# --- Jinja2 Environment Setup ---

def create_jinja_env() -> jinja2.Environment:
    """Creates and configures the global Jinja2 environment."""
    # Use the directory of the current file as the search path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(searchpath=current_dir), # For loading templates from files if needed later
        undefined=jinja2.StrictUndefined, # Fail on undefined variables in templates
        autoescape=False, # Assuming text output, not HTML. Change if needed.
        trim_blocks=True, # Remove leading/trailing whitespace from blocks
        lstrip_blocks=True # Remove leading whitespace from the start of a line to a block
    )
    # Add custom filters or globals here if any
    # env.filters['my_custom_filter'] = my_custom_filter_function
    return env

JINJA_ENV = create_jinja_env()

# --- Jinja2 Template Rendering Helper ---

def render_template_string(
    template_str: Optional[str],
    template_variables: Dict[str, Any],
    template_name: str # For error reporting
) -> Optional[str]:
    """
    Renders a Jinja2 template string with the given variables.
    Returns the rendered string, or None if template_str is None.
    Logs and exits on Jinja2 rendering errors.
    """
    if template_str is None:
        logger.debug(f"Template '{template_name}' is None, skipping rendering.")
        return None

    try:
        template = JINJA_ENV.from_string(str(template_str)) # Ensure it's a string
        rendered_text = template.render(template_variables)
        logger.debug(f"Successfully rendered template '{template_name}'.")
        return rendered_text
    except jinja2.exceptions.TemplateError as e:
        error_msg = f"Error rendering '{template_name}' template: {e}"
        if hasattr(e, 'lineno') and e.lineno is not None: # Check lineno is not None
            error_msg += f" (near line {e.lineno})"
        logger.error(error_msg)
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during '{template_name}' templating: {e}")
        sys.exit(1)


# --- Configuration ---

# Default system instruction template (can be overridden by --conf-system-instruction)
# This string is treated as a Jinja2 template.
DEFAULT_SYSTEM_INSTRUCTION = """
Analyze the given document and provide a concise summary.
{% if topic is defined %}Focus on the topic: {{ topic }}.{% endif %}
"""

# Default user instruction template (can be overridden by --conf-user-instruction)
# This string is treated as a Jinja2 template.
DEFAULT_USER_INSTRUCTION = """<document>
{{ document }}
</document>

{% if input is defined %}
User Query: {{ input }}
{% endif %}
"""

# Default configuration parameters
# Values here should be of the correct final type
DEFAULT_CONFIG: Dict[str, Any] = {
    "model": "gemini-2.5-flash-preview-04-17",
    "temperature": 0.1,
    "response-mime-type": "text/plain",
    "max-output-tokens": None, # Example: Can be overridden by config file or CLI
    "enable-feature-x": False, # Hypothetical boolean flag for testing (not passed to API)
    "system-instruction": DEFAULT_SYSTEM_INSTRUCTION, # System instruction is a config param, its VALUE is a template
    "user-instruction": DEFAULT_USER_INSTRUCTION, # User instruction is now also a config param and a template
    # Add other default config options here that map to types.GenerateContentConfig
    # e.g., "top-p": None, "top-k": None, "stop-sequences": None, "candidate-count": None
}

# Schema for configuration parameter types
# Used for converting string values from CLI or ensuring types from config file
CONFIG_TYPES: Dict[str, type] = {
    "model": str,
    "temperature": float,
    "response-mime-type": str,
    "max-output-tokens": int,
    "enable-feature-x": bool, # Hypothetical, not passed to API
    "system-instruction": str, # System instruction is a string (which is then templated)
    "user-instruction": str, # User instruction is now also a string (which is then templated)
    # Add types for other config options here
    # "top-p": float, "top-k": int, "stop-sequences": list, "candidate-count": int
}

# Configuration file path
CONFIG_FILE_DIR = pathlib.Path.home() / ".config" / "genai_cli"
CONFIG_FILE_PATH = CONFIG_FILE_DIR / "config.toml"

# --- Configuration Generation ---

def format_toml_value_line(name: str, value: Any) -> str:
    """Formats a single key-value pair into a TOML string line."""
    # Use toml.dumps on a tiny dictionary to get correct TOML value formatting
    try:
        # toml.dumps returns a string like 'name = "value"\n' or 'name = """..."""\n'
        # We just need the 'name = value' part.
        # toml.dumps handles quoting, escaping, multi-line strings correctly.
        temp_dict = {name: value}
        toml_string = toml.dumps(temp_dict).strip()
        # toml.dumps might add [table] headers for complex types, but our config is flat.
        # It should produce "key = value".
        # Find the line that actually contains the key=value pair
        value_line = next((line for line in toml_string.splitlines() if line.strip().startswith(f'{name} =')), None)

        if value_line:
            return value_line
        else:
            # Fallback if toml.dumps output is unexpected (shouldn't happen for simple types)
            logger.warning(f"Could not format value '{value!r}' for '{name}' using toml.dumps.")
            return f"{name} = <error_formatting>"

    except Exception as e:
        logger.error(f"Error formatting value '{value!r}' for '{name}' using toml.dumps: {e}")
        return f"{name} = <error_formatting>"


def generate_default_config_toml():
    """Generates a self-descriptive TOML configuration string with default values."""
    output = []
    output.append("# Default configuration for genai_cli script")
    output.append("# This file is loaded from ~/.config/genai_cli/config.toml")
    output.append("# Settings here override script defaults but are overridden by command-line --conf-<name> arguments.")
    output.append("") # Blank line

    # Iterate through default config items to generate TOML with comments
    for name, default_value in DEFAULT_CONFIG.items():
        param_type = CONFIG_TYPES.get(name, type(default_value))
        type_name = param_type.__name__ if param_type else "Any"

        output.append(f"# Parameter: {name}")
        output.append(f"# Type: {type_name}")
        output.append(f"# Default: {default_value!r}") # Use !r for representation

        if default_value is None:
            # TOML doesn't have a direct 'None'. Comment out the line with a placeholder.
            output.append(f"# {name} = <value>")
        else:
            # Use the helper to format the TOML line correctly
            output.append(format_toml_value_line(name, default_value))

        output.append("") # Blank line after each parameter block

    print("\n".join(output)) # Print the generated TOML to stdout

# --- Logging Setup ---
# Basic configuration will be done in __main__ to allow setting level via CLI later if needed
# Logger instance
logger = logging.getLogger(__name__)


# --- Helper Functions ---

def read_file_content(filepath: str) -> str:
    """Reads the content of a file."""
    try:
        # Use absolute path in case the script changes directory
        abs_filepath = os.path.abspath(filepath)
        logger.debug(f"Attempting to read file: {abs_filepath}")
        with open(abs_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            logger.debug(f"Successfully read file: {abs_filepath}")
            return content
    except FileNotFoundError:
        logger.error(f"File not found at '{filepath}' (resolved to '{abs_filepath}')")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading file '{filepath}' (resolved to '{abs_filepath}'): {e}")
        sys.exit(1)

def usage(config: Dict[str, Any]):
    """Prints dynamic usage information including config and template parameters."""
    script_name = os.path.basename(sys.argv[0])

    print(f"Usage: {script_name} [options] [--conf-param value ...] [--template-var value ...]")
    print("\nOptions:")
    print("  -h, --help            Show this help message and exit")
    print("  --debug               Enable debug logging output")
    print("  --generate-config     Generate a default config file (TOML) to stdout and exit")
    print("  --show-prompt         Render and print the final templated prompt (system + user) to stdout and exit")

    print("\nConfiguration:")
    print("  Configuration is loaded in the following order of precedence (later overrides earlier):")
    print("  1. Script defaults.")
    print(f"  2. Configuration file (TOML format): {CONFIG_FILE_PATH}")
    print("  3. Command-line arguments (--conf-<name> value).")
    print("  These parameters control the model behavior and generation settings.")
    print("  For string parameters like 'system-instruction' or 'user-instruction',")
    print("  a value starting with `@:` will be interpreted as a file path, and the")
    print("  file content will be loaded as the parameter value.")


    print("\nConfiguration Parameters (--conf-<name> value):")
    # Display effective defaults after considering DEFAULT_CONFIG (types are important here)
    for name, default_value in DEFAULT_CONFIG.items():
        param_type = CONFIG_TYPES.get(name, type(default_value))
        type_name = param_type.__name__ if param_type else "Any"
        # Display the effective default value from the loaded config
        effective_value = config.get(name, default_value)
        # Truncate long string defaults for display
        display_value = str(effective_value)
        if len(display_value) > 50:
             display_value = display_value[:47] + "..."
        # Use !r for representation, and escape curly braces for f-string if they appear in the value string
        display_value_repr = repr(display_value).replace('{', '{{').replace('}', '}}')
        print(f"  --conf-{name:<20} (type: {type_name}, default: {display_value_repr})")


    print("\nTemplate Variables (--<name> value or --<name> @:path/to/file):")
    print("  These variables are passed as context to the Jinja2 prompt templates (system and user instructions).")
    print("  Jinja2 syntax: {{ variable }} for variables, {% ... %} for logic.")
    print("  Automatic listing of variables used in templates is not supported.")
    print("  Refer to your specific system/user instruction templates for required variables.")
    print("  Use --<name> @:path/to/file to load variable content from a file.")
    print("  Paths can be absolute (`@:/home/user/doc.txt`) or relative (`@:./report.md`).")


    print("\nExamples:")
    print(f"  {script_name} --document \"Summary of report...\" --input \"What are the key findings?\"")
    print(f"  {script_name} --document @:./report.txt --input @:/home/user/questions.txt --conf-temperature 0.8")
    print(f"  {script_name} --conf-model \"gemini-1.5-pro-latest\" --conf-max-output-tokens 100 --conf-system-instruction \"Act as a helpful assistant about {{ topic }}.\" --topic \"Python\"")
    print(f"  {script_name} --conf-user-instruction \"Summarize this {{ document_type }}:\\n{{ document }}\" --document-type \"article\" --document @:./article.txt")
    print(f"  {script_name} --conf-system-instruction @:./system_template.j2 --conf-user-instruction @:./user_template.j2 --document @:./doc.txt")
    print(f"  {script_name} --show-prompt --document @:./doc.txt --topic \"AI\"")
    print("\nNote: Ensure GOOGLE_API_KEY environment variable is set.")
    print(f"      Create a default config at {CONFIG_FILE_PATH}, e.g.:")
    print("      model = \"gemini-1.5-pro-latest\"")
    print("      temperature = 0.5")
    print("      system-instruction = \"Your custom default system instruction about {{ subject }}\"")
    print("      user-instruction = \"Summarize the following {{ item }}:\\n{{ content }}\"")
    print("      # Or load from a file:")
    print("      # system-instruction = \"@:./default_system.j2\"")
    print("      # user-instruction = \"@:/home/user/default_user.j2\"")

# --- Configuration Loading and Type Conversion ---

def load_config_from_file(filepath: pathlib.Path) -> Dict[str, Any]:
    """Loads configuration from a TOML file."""
    config: Dict[str, Any] = {}
    if filepath.exists():
        logger.info(f"Loading configuration from {filepath}")
        try:
            with open(filepath, "rb") as f: # tomllib expects bytes
                config = tomllib.load(f)
            logger.debug(f"Config loaded from file: {config}")
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding TOML from {filepath}: {e}")
            # Don't exit here if just loading for help/list flags, let main decide
            raise # Re-raise to be caught by main if needed
        except Exception as e:
            logger.error(f"Error reading config file {filepath}: {e}")
            # Don't exit here if just loading for help/list flags
            raise # Re-raise to be caught by main if needed
    else:
        logger.info(f"Configuration file not found at {filepath}. Using defaults and/or CLI args.")
    return config

def _convert_config_values(
    config_data: Dict[str, Any],
    types_schema: Dict[str, type],
    source_name: str  # For logging, e.g., "file", "CLI"
) -> Dict[str, Any]:
    """
    Converts values in config_data to types specified in types_schema.
    Handles None values appropriately.
    Returns the converted dictionary. Raises ValueError or TypeError on failure.
    Note: This function does NOT resolve file paths for template strings.
          That is handled in a separate step after loading.
    """
    converted_config: Dict[str, Any] = {}
    for name, value in config_data.items():
        if name not in types_schema:
            converted_config[name] = value
            logger.debug(f"Config parameter '{name}' from {source_name} has no defined type in schema, using value '{value}' as is.")
            continue

        expected_type = types_schema[name]

        if value is None: # If the value is None, it's valid if the parameter is optional (e.g. max-output-tokens)
            converted_config[name] = None
            continue

        # If value is already of the exact expected type (common for DEFAULT_CONFIG or tomli parsed values)
        if isinstance(value, expected_type):
            # Special case: if expected is float and value is int, we still want to convert to float for consistency.
            if expected_type == float and isinstance(value, int):
                converted_config[name] = float(value)
            else:
                converted_config[name] = value
            continue

        original_value_for_error = value
        try:
            if expected_type == bool:
                if isinstance(value, str):
                    if value.lower() in ['true', 'yes', '1', 'on']:
                        converted_value = True
                    elif value.lower() in ['false', 'no', '0', 'off']:
                        converted_value = False
                    else:
                        raise ValueError(f"Boolean value expected (true/false/yes/no/1/0), got '{value}'")
                elif isinstance(value, (int, float)) and value in [0, 1]: # Allow 0/1 as bool
                    converted_value = bool(value)
                else: # If not string or 0/1, and not already bool (caught by isinstance above)
                    raise ValueError(f"Cannot convert type {type(value).__name__} to bool for '{name}'")
            # Add handling for list types if needed for stop-sequences etc.
            # elif expected_type == list:
            #     if isinstance(value, str):
            #         # Simple comma-separated string to list conversion
            #         converted_value = [item.strip() for item in value.split(',')]
            #     elif isinstance(value, list):
            #          converted_value = value # Already a list from TOML
            #     else:
            #          raise ValueError(f"Cannot convert type {type(value).__name__} to list for '{name}'")
            else: # For other types (int, float, str)
                converted_value = expected_type(value)

            converted_config[name] = converted_value

        except (ValueError, TypeError) as e:
             # Re-raise with more context
             raise type(e)(
                 f"Error converting config parameter '{name}' from {source_name}: "
                 f"Expected {expected_type.__name__}, got '{original_value_for_error}' "
                 f"(type: {type(original_value_for_error).__name__}). Original error: {e}"
             ) from e

    return converted_config

def _resolve_config_file_paths(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Checks specific configuration values (like instruction templates) and,
    if they are strings starting with `@:`, loads their content from the specified file.
    Modifies the dictionary in place.
    """
    resolved_config = config_dict # Modify in place
    template_keys_to_resolve = ["system-instruction", "user-instruction"] # Add other keys if they can be templates loaded from files

    for key in template_keys_to_resolve:
        value = resolved_config.get(key)
        # Check if the value is a string and matches the file path convention
        if isinstance(value, str):
            filepath = None
            if value.startswith('@:'):
                filepath = value[2:] # Remove '@:' prefix

            if filepath:
                logger.info(f"Attempting to load template for '{key}' from file specified in config: '{filepath}'")
                # read_file_content handles errors and exits, so no need for try/except here
                resolved_config[key] = read_file_content(filepath)
                logger.info(f"Successfully loaded template for '{key}' from file: {filepath}")

    return resolved_config


def load_effective_config(args: List[str]) -> Dict[str, Any]:
    """
    Loads configuration from defaults, file, and CLI --conf- arguments.
    Does NOT process template arguments or exit on their errors.
    Returns the final merged configuration dictionary.
    """
    # 1. Start with script defaults (already correctly typed)
    final_config = DEFAULT_CONFIG.copy()
    logger.debug(f"Initial config from defaults: {final_config}")

    # 2. Load and merge config from file
    try:
        raw_file_config = load_config_from_file(CONFIG_FILE_PATH)
        if raw_file_config: # Only convert and update if file_config is not empty
            # Convert types from file config
            typed_file_config = _convert_config_values(raw_file_config, CONFIG_TYPES, "file")
            # Resolve file paths within the file config values *before* merging
            resolved_file_config = _resolve_config_file_paths(typed_file_config)
            final_config.update(resolved_file_config)
            logger.debug(f"Config after merging file settings: {final_config}")
    except (tomllib.TOMLDecodeError, ValueError, TypeError) as e:
         # load_config_from_file or _convert_config_values already logged the error
         sys.exit(1)


    # 3. Extract and merge CLI configurations (--conf- args only)
    cli_raw_conf_params: Dict[str, str] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        # We only care about --conf- args here
        if arg.startswith('--conf-'):
            if i + 1 >= len(args):
                 logger.error(f"Error: Configuration argument '{arg}' requires a value.")
                 sys.exit(1)
            conf_name = arg[len('--conf-'):] # Remove '--conf-' prefix
            if not conf_name:
                 logger.error(f"Error: Configuration argument '{arg}' is missing a name after '--conf-'.")
                 sys.exit(1)
            cli_raw_conf_params[conf_name] = args[i+1]
            logger.debug(f"Parsed raw CLI config: {conf_name}={cli_raw_conf_params[conf_name]}")
            i += 2 # Consume both arg and value
        else:
            # Skip other arguments (template args, flags like --help, --debug)
            i += 1 # Consume just the arg

    if cli_raw_conf_params: # Only convert and update if CLI params exist
        try:
            # Convert types from CLI config
            typed_cli_config = _convert_config_values(cli_raw_conf_params, CONFIG_TYPES, "CLI")
            # Resolve file paths within the CLI config values *before* merging
            resolved_cli_config = _resolve_config_file_paths(typed_cli_config)
            final_config.update(resolved_cli_config)
            logger.debug(f"Config after merging CLI settings: {final_config}")
        except (ValueError, TypeError) as e:
            # _convert_config_values already logged the error
            sys.exit(1)


    logger.info(f"Effective Configuration: {final_config}")
    return final_config

# --- Argument Parsing Pipeline Stages (Generators) ---

def pair_args(args: List[str]) -> Generator[Tuple[str, str], None, None]:
    """
    Generator that takes a list of raw arguments and yields (name_arg, value_arg) pairs.
    Assumes args are already filtered to be only potential template args.
    Validates that arguments start with '--' and have a following value.
    """
    i = 0
    while i < len(args):
        name_arg = args[i]
        # This check should ideally not be needed if args are pre-filtered,
        # but keeping for robustness.
        if not name_arg.startswith('--'):
             logger.error(f"Internal Error: Non '--' argument passed to pair_args: '{name_arg}'")
             sys.exit(1)

        if i + 1 >= len(args):
            logger.error(f"Error: Argument '{name_arg}' requires a value.")
            sys.exit(1)

        value_arg = args[i+1]
        yield (name_arg, value_arg)
        i += 2

def process_template_values(arg_pairs: Generator[Tuple[str, str], None, None]) -> Generator[Tuple[str, str], None, None]:
    """
    Generator that takes (name_arg, value_arg) pairs, processes the value
    (handling @: for file paths), and yields (clean_name, processed_value) pairs.
    """
    for name_arg, value_arg in arg_pairs:
        name = name_arg[2:] # Remove the '--' prefix
        if value_arg.startswith('@:'):
            filepath = value_arg[2:] # Remove '@:' prefix
            processed_value = read_file_content(filepath)
        else:
            processed_value = value_arg
        yield (name, processed_value)

# --- Argument Parsing Orchestration ---

def parse_template_args(args: List[str]) -> Dict[str, str]:
    """
    Parses command-line arguments that are NOT --conf- or known flags,
    treating them as template variables (--name value).
    """
    # Filter out --conf- args and known flags like --debug, --help, --generate-config
    # Note: --help and --generate-config are handled before this function is called,
    # but we filter them here defensively.
    template_args_list: List[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith('--conf-'):
            # Skip --conf- args and their values
            i += 2
        elif arg in ['--debug', '-h', '--help', '--generate-config', '--show-prompt']:
             # Skip known flags
             i += 1
        elif arg.startswith('--'):
            # Assume it's a template arg
            if i + 1 >= len(args):
                 logger.error(f"Error: Template argument '{arg}' requires a value.")
                 sys.exit(1)
            template_args_list.append(arg)
            template_args_list.append(args[i+1])
            logger.debug(f"Identified template arg: {arg} {args[i+1]}")
            i += 2
        else:
            logger.error(f"Error: Unexpected argument '{arg}'. Arguments must start with '--'.")
            sys.exit(1)

    # Process template arguments
    arg_pairs_generator = pair_args(template_args_list)
    processed_pairs_generator = process_template_values(arg_pairs_generator)
    template_variables = dict(processed_pairs_generator)
    logger.info(f"Template Variables: {template_variables}")
    return template_variables

# --- Prompt Display Function ---

def show_rendered_prompt(config: Dict[str, Any], template_variables: Dict[str, str]):
    """
    Renders the system and user instruction templates and prints them to stdout, then exits.
    """
    logger.info("Rendering prompt for display (--show-prompt)...")

    system_instruction_template_str = config.get("system-instruction")
    user_instruction_template_str = config.get("user-instruction")

    rendered_system_instruction = render_template_string(
        system_instruction_template_str,
        template_variables,
        "system-instruction (for --show-prompt)"
    ) or "" # Default to empty string if None, ensuring XML tags are complete

    rendered_user_instruction = render_template_string(
        user_instruction_template_str,
        template_variables,
        "user-instruction (for --show-prompt)"
    ) or "" # Default to empty string if None

    # Output format
    # Ensure there's a newline after the opening tag and before the closing tag
    # if the content itself is multi-line or non-empty.
    # If content is empty, it will be <tag>\n</tag>
    
    # Using .strip() on the rendered content before placing it between newlines
    # ensures that if the content is empty or just whitespace, it becomes
    # <tag>\n</tag>
    # If it has content, it becomes <tag>\ncontent\n</tag>
    
    system_content_processed = rendered_system_instruction.strip()
    user_content_processed = rendered_user_instruction.strip()

    system_block = f"<system_instruction>\n{system_content_processed}\n</system_instruction>"
    user_block = f"<user_instruction>\n{user_content_processed}\n</user_instruction>"
    
    # If a template was not defined (rendered as empty string) and then stripped,
    # it results in <tag>\n\n</tag>. This is acceptable and clearly shows emptiness.

    final_output = f"{system_block}\n{user_block}"

    print(final_output)
    sys.exit(0)

# --- Generation Sub-Functions ---

def prepare_prompt_contents(config: Dict[str, Any], template_variables: Dict[str, str]) -> List[types.Content]:
    """
    Generates the list of Content objects for the API call by applying
    template variables to the defined prompt templates (excluding system instruction).
    The user instruction template is retrieved from the config. Uses Jinja2.
    """
    # Get the user instruction template from config
    user_instruction_template_str = config.get("user-instruction")

    user_instruction_text = render_template_string(
        user_instruction_template_str,
        template_variables,
        "user-instruction"
    )
    if user_instruction_text is None: # render_template_string returns None if template_str is None
        user_instruction_text = "" # Default to empty string for API content
    logger.debug(f"Templated user instruction part:\n{user_instruction_text}")

    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=user_instruction_text)]),
    ]
    return contents

def prepare_generate_content_config_dict(
    config: Dict[str, Any],
    template_variables: Dict[str, str]
) -> Dict[str, Any]:
    """
    Generates the configuration dictionary for the generate_content API call
    from the parsed configuration. This dictionary matches the structure
    expected by types.GenerateContentConfig.
    Applies template variables to the system instruction using Jinja2.
    """
    # Get parameters from the final_config that map to GenerateContentConfig
    # These should already be correctly typed and defaults applied.
    temperature = config.get("temperature")
    response_mime_type = config.get("response-mime-type")
    max_output_tokens = config.get("max-output-tokens") # Will be None or int
    system_instruction_template_str = config.get("system-instruction") # This is the template string
    template_name = "system-instruction" # Name for error reporting

    logger.info(f"Using temperature: {temperature}")
    logger.info(f"Using response_mime_type: {response_mime_type}")
    if max_output_tokens is not None:
        logger.info(f"Using max_output_tokens: {max_output_tokens}")

    # Template-expand the system instruction
    system_instruction_text = render_template_string(
        system_instruction_template_str,
        template_variables,
        "system-instruction"
    )
    # system_instruction_text can be None, which is valid for the API.
    # render_template_string returns None if system_instruction_template_str was None.
    logger.debug(f"Templated System Instruction:\n{system_instruction_text or 'None'}")

    # Build the dictionary for the 'config' argument of generate_content
    # Only include keys if the value is not None, unless None is a valid value (like max_output_tokens)
    # The SDK handles None for optional parameters correctly.
    generate_config_dict: Dict[str, Any] = {
        "temperature": temperature,
        "response_mime_type": response_mime_type,
        "max_output_tokens": max_output_tokens, # None is a valid value here
        "system_instruction": system_instruction_text, # Pass the TEMPLATED string (or None)
        # Add other config parameters here if they are added to DEFAULT_CONFIG and CONFIG_TYPES
        # e.g., "top_p": config.get("top-p"),
        # e.k., "top_k": config.get("top-k"),
        # e.g., "stop_sequences": config.get("stop-sequences"),
        # e.g., "candidate_count": config.get("candidate-count"),
    }
    return generate_config_dict


def execute_generation_stream(
    client: genai.Client,
    model_name: str,
    contents: List[types.Content],
    config_dict: Dict[str, Any]
) -> Generator[types.GenerateContentResponse, None, None]:
    """
    Executes the streaming generation API call using the new SDK client.models interface.
    """
    logger.info(f"Executing streaming generation API call for model '{model_name}'...")
    logger.debug(f"API Call Config: {config_dict}")

    # Use the new SDK pattern: client.models.generate_content_stream
    return client.models.generate_content_stream(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(**config_dict) # Pass the config dictionary as GenerateContentConfig
        # Note: system_instruction is now inside the config_dict
    )

def stream_output(stream_generator: Generator[types.GenerateContentResponse, None, None]) -> None:
    """
    Consumes the generator from the API call and streams the text output to stdout.
    """
    logger.info("Streaming content to stdout...")
    try:
        for chunk in stream_generator:
            # Check for empty text in chunk, which can happen
            if chunk.text:
                print(chunk.text, end="")
        print() # Add a newline at the end if not already handled by last chunk
        sys.stdout.flush() # Ensure output is flushed
        logger.info("Generation streaming finished.")
    except types.generation_types.BlockedPromptException as e:
        logger.error(f"Prompt was blocked: {e}")
        # Access block_reason from prompt_feedback
        block_reason = e.prompt_feedback.block_reason.name if e.prompt_feedback and e.prompt_feedback.block_reason else 'Unknown'
        print(f"\nERROR: Prompt was blocked. Reason: {block_reason}", file=sys.stderr)
        sys.exit(1) # Exit on blocked prompt
    except types.generation_types.StopCandidateException as e:
        logger.error(f"Generation stopped prematurely for a candidate: {e}")
        # This usually means a candidate was stopped due to safety or other reasons.
        # The content generated so far might be partial.
        # Access finish_reason from the candidate
        finish_reason = e.candidate.finish_reason.name if hasattr(e, 'candidate') and e.candidate.finish_reason else 'Unknown'
        print(f"\nWARNING: Generation may be incomplete. Reason: {finish_reason}", file=sys.stderr)
        # Don't necessarily exit, partial output might be useful
    except Exception as e:
        # Catch potential errors during streaming itself (e.g., network issues mid-stream)
        logger.error(f"Error during streaming output: {e}")
        # Consider more specific API error types from google.api_core.exceptions if needed
        # e.g. from google.api_core import exceptions
        # if isinstance(e, exceptions.GoogleAPIError):
        #     logger.error(f"Google API Error: {e.message}")
        raise # Re-raise the exception after logging


# --- Main Generation Orchestration ---

def generate(config: Dict[str, Any], template_variables: Dict[str, str]):
    """
    Orchestrates the generation process: prepares prompt, prepares config,
    executes API call, and streams output. Handles API errors.
    """
    # Use GOOGLE_API_KEY as preferred by the new SDK
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        # Fallback to GEMINI_API_KEY for backward compatibility if needed, but warn
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
             logger.warning("Using deprecated GEMINI_API_KEY environment variable. Please use GOOGLE_API_KEY instead.")
        else:
            logger.error("Error: GOOGLE_API_KEY environment variable not set.")
            sys.exit(1)

    # Initialize the client using the new SDK pattern
    # The client picks up the API key from the env var if not passed explicitly
    # Passing it explicitly here for clarity since we checked it.
    client = genai.Client(api_key=api_key)
    logger.debug("GenAI client initialized.")

    # 1. Prepare prompt contents (still uses template variables)
    # Pass config here to get the user instruction template
    contents = prepare_prompt_contents(config, template_variables)

    # 2. Prepare the configuration dictionary for the API call
    # This includes parameters like temperature, max_output_tokens, and system_instruction
    # Pass template_variables here to template the system instruction
    generate_config_dict = prepare_generate_content_config_dict(config, template_variables)

    # Get the model name from the final config
    model_name = config.get("model", DEFAULT_CONFIG["model"])
    logger.info(f"Using model: {model_name}")
    logger.debug(f"GenerateContentConfig dictionary for API call: {generate_config_dict}")


    # 3. Execute the API call to get the stream
    try:
        stream_generator = execute_generation_stream(
            client,
            model_name,
            contents,
            generate_config_dict # Pass the config dictionary
        )
        # 4. Stream the output
        stream_output(stream_generator)

    except Exception as e:
        # This catches errors from execute_generation_stream or stream_output
        # stream_output already logs streaming errors, but this catches initial API errors too
        logger.error(f"An error occurred during the generation process: {e}")
        # More specific error handling can be added here for API errors
        # e.g. from google.api_core.exceptions
        # if isinstance(e, exceptions.GoogleAPIError):
        #      logger.error(f"API Error details: {e.message}")
        sys.exit(1)


# --- Main Execution ---

if __name__ == "__main__":
    # Configure basic logging early, but with a high level initially
    # This prevents INFO/DEBUG logs from config loading appearing during --help/--generate-config
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr)

    # Ensure config directory exists for user convenience if they want to create a file
    try:
        CONFIG_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Non-critical, just log if we can't create it (e.g. permissions)
        logger.warning(f"Could not create config directory {CONFIG_FILE_DIR}: {e}")

    # --- Handle early exit flags ---
    args_list = list(sys.argv[1:]) # Exclude script name

    if '--generate-config' in args_list:
        # This flag doesn't require loading the full config first
        logger.info("Generating default configuration TOML to stdout.") # This log will appear as level is WARNING
        generate_default_config_toml()
        sys.exit(0)

    # Load effective config first, as it's needed for help flag and show-prompt
    try:
        effective_config = load_effective_config(args_list) 
    except (tomllib.TOMLDecodeError, ValueError, TypeError) as e:
         # load_effective_config already logs the error, just exit
         sys.exit(1)


    if '-h' in args_list or '--help' in args_list:
        usage(effective_config) # Pass the loaded config to usage
        sys.exit(0)

    # Parse template arguments. These are needed for --show-prompt and for generation.
    # parse_template_args filters out flags like --debug, --conf-, --help, --show-prompt etc.
    template_vars = parse_template_args(args_list)

    if '--show-prompt' in args_list:
        # Set log level appropriately for show_prompt, so its logs appear.
        # If --debug is present, DEBUG level is used. Otherwise, INFO.
        log_level_for_show_prompt = logging.DEBUG if '--debug' in args_list else logging.INFO
        logging.basicConfig(level=log_level_for_show_prompt, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr, force=True)
        show_rendered_prompt(effective_config, template_vars)
        # show_rendered_prompt calls sys.exit(0), so this is technically redundant but good for clarity.
        sys.exit(0) 

    # --- Continue with normal execution if no early exit flag was found ---

    # Now that flags are handled, determine the actual desired logging level for generation
    log_level = logging.INFO
    if '--debug' in args_list: # Check args_list as sys.argv still contains all args
        log_level = logging.DEBUG
        
    # Reconfigure logging with the correct level for normal execution
    # Use force=True to override the initial basicConfig
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr, force=True)


    # Pass variables to the generate function
    generate(effective_config, template_vars)
