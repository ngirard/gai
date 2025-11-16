"""Command-line interface for gai."""

import argparse
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from .template_catalog import TemplateRecord

from .config import (
    CONFIG_FILE_DIR,
    CONFIG_FILE_PATH,
    CONFIG_TYPES,
    DEFAULT_CONFIG,
    REPO_CONFIG_RELATIVE_PATH,
    get_repo_config_path,
    read_file_content,
)
from .exceptions import CliUsageError, TemplateError
from .template_interface import TemplateInterface, build_template_interface
from .templates import create_jinja_env_from_catalog, render_system_instruction, render_user_instruction

logger = logging.getLogger(__name__)


def _repo_config_display_path() -> str:
    repo_config_path = get_repo_config_path()
    if repo_config_path is not None:
        return str(repo_config_path)
    return f"<git repo root>/{REPO_CONFIG_RELATIVE_PATH}"


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

    if part == "system" or part is None:
        rendered_system_instruction = render_system_instruction(config, template_variables)
        system_content_processed = (rendered_system_instruction or "").strip()
    else:
        system_content_processed = ""

    if part == "user" or part is None:
        rendered_user_instruction = render_user_instruction(config, template_variables)
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
    repo_config_hint = _repo_config_display_path()

    parser = argparse.ArgumentParser(
        prog="gai",
        description="Google Gemini prompting tool with flexible CLI, templating, and configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            f"""
            Configuration layers (later overrides earlier):
              1. Script defaults.
              2. User configuration file: {CONFIG_FILE_PATH}
              3. Repository configuration file (if inside a Git repo): {repo_config_hint}
              4. Command-line arguments (--conf-<name> value).

            Template variables:
              • Use --<name> VALUE on any command to inject data into prompts.
              • Prefix values with '@:' to load from a file.
            """
        ).strip(),
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
    generate_parser.add_argument(
        "--capture-tag",
        metavar="TAG",
        help="Capture only the text between <TAG> and </TAG> in the streamed response",
    )
    generate_parser.add_argument(
        "--output-file",
        metavar="PATH",
        help="Write captured output to PATH instead of stdout (requires --capture-tag)",
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
    render_parser.add_argument(
        "template_name",
        nargs="?",
        help="Optional user instruction template logical name (shorthand for -t/--template)",
    )
    render_parser.add_argument(
        "-t",
        "--template",
        metavar="LOGICAL_NAME",
        help="User instruction template logical name (shortcut for --conf-user-instruction-template)",
    )

    # Add config and template args to render_parser
    _add_config_and_template_args(render_parser)

    # template list
    list_parser = template_subparsers.add_parser(
        "list",
        help="List discovered templates in catalog order",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument(
        "--tier",
        choices=["project", "user", "builtin"],
        help="Filter templates by tier",
    )
    list_parser.add_argument(
        "--filter",
        metavar="SUBSTRING",
        help="Filter templates whose logical name contains this substring",
    )
    list_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    list_parser.add_argument(
        "--interface",
        action="store_true",
        help="Include inferred I/O/C/M information for each template",
    )
    _add_config_and_template_args(list_parser)

    # template browse
    browse_parser = template_subparsers.add_parser(
        "browse",
        help="Interactively browse templates and select one (preview enabled by default)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    browse_parser.add_argument(
        "--tier",
        choices=["project", "user", "builtin"],
        help="Filter templates by tier before browsing",
    )
    browse_parser.add_argument(
        "--filter",
        metavar="SUBSTRING",
        help="Filter templates whose logical name contains this substring before browsing",
    )
    browse_parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable preview pane (preview is enabled by default)",
    )
    _add_config_and_template_args(browse_parser)

    inspect_parser = template_subparsers.add_parser(
        "inspect",
        help="Inspect template inputs, controls, mechanisms, and outputs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    inspect_parser.add_argument("logical_name", help="Logical template name to inspect")
    _add_config_and_template_args(inspect_parser)

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

                _apply_iocm_aliases(template_vars, name, value)
                i += 2
            else:
                raise CliUsageError(f"Template argument '{arg}' requires a value.")
        else:
            raise CliUsageError(f"Unexpected argument '{arg}'. Template variables must start with '--'.")

    return template_vars


def _apply_iocm_aliases(template_vars: dict[str, str], name: str, value: str) -> None:
    """Populate implicit I_/C_ aliases for CLI-provided template variables."""

    if name.startswith("I_") or name.startswith("C_"):
        return

    inferred_input = f"I_{name}"
    inferred_control = f"C_{name}"

    template_vars.setdefault(inferred_input, value)
    template_vars.setdefault(inferred_control, value)


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
    print(f"# Or to a repo-specific file: <git repo root>/{REPO_CONFIG_RELATIVE_PATH}")
    print()
    print(tomli_w.dumps(config_to_dump))


def handle_config_path() -> None:
    """Show the configuration file path."""
    print(f"User configuration file path: {CONFIG_FILE_PATH}")
    if CONFIG_FILE_PATH.exists():
        print("Status: exists")
    else:
        print("Status: not found")

    repo_config_path = get_repo_config_path()
    if repo_config_path is not None:
        print(f"Repository configuration file path: {repo_config_path}")
        if repo_config_path.exists():
            print("Status: exists")
        else:
            print("Status: not found")
    else:
        print(f"Repository configuration file path: <git repo root>/{REPO_CONFIG_RELATIVE_PATH}")
        print("Status: not available outside a Git repository")


# ===== Template subcommand handlers =====


def handle_template_list(config: dict[str, Any], parsed: argparse.Namespace) -> None:
    """Handle the 'gai template list' command.

    Lists all discovered templates with optional filtering by tier and substring.
    Supports both human-readable table format and JSON output.

    Args:
        config: Effective configuration dictionary
        parsed: Parsed command-line arguments
    """
    import json

    from .template_catalog import build_template_catalog

    # Build catalog from configuration
    catalog = build_template_catalog(config)
    records = list(catalog.records)

    # Apply tier filter if specified
    if hasattr(parsed, "tier") and parsed.tier:
        records = [r for r in records if r.tier == parsed.tier]

    # Apply substring filter if specified
    if hasattr(parsed, "filter") and parsed.filter:
        substring = parsed.filter
        records = [r for r in records if substring in r.logical_name_full]

    # Handle empty results
    if not records:
        if parsed.format == "json":
            print("[]")
        else:
            print("No templates found. Check your template paths in configuration.")
        return

    interface_map: dict[str, TemplateInterface] = {}
    interface_summaries: dict[str, str] = {}
    if parsed.interface:
        env = create_jinja_env_from_catalog(catalog.records)
        for record in records:
            try:
                interface = build_template_interface(
                    config,
                    record.logical_name_full,
                    catalog=catalog.records,
                    jinja_env=env,
                )
                interface_map[record.logical_name_full] = interface
                interface_summaries[record.logical_name_full] = _summarize_interface_for_table(interface)
            except TemplateError as exc:
                interface_summaries[record.logical_name_full] = f"Error: {exc}"

    # Output based on format
    if parsed.format == "json":
        # JSON output
        output_data = []
        for record in records:
            data = {
                "logical_name": record.logical_name_full,
                "tier": record.tier,
                "relative_path": record.relative_path.as_posix(),
                "absolute_path": str(record.absolute_path),
                "root_index": record.root_index,
                "extension": record.extension,
            }
            if parsed.interface:
                interface = interface_map.get(record.logical_name_full)
                if interface:
                    data["interface"] = {
                        "inputs": sorted(interface.inputs),
                        "controls": sorted(interface.controls),
                        "mechanisms": sorted(interface.mechanisms),
                        "outputs": sorted(interface.outputs),
                    }
                else:
                    data["interface"] = interface_summaries.get(record.logical_name_full)
            output_data.append(data)
        print(json.dumps(output_data, indent=2))
    else:
        # Table output
        rows = []
        for record in records:
            row = [record.tier, record.logical_name_full, record.relative_path.as_posix()]
            if parsed.interface:
                row.append(interface_summaries.get(record.logical_name_full, "-"))
            rows.append(row)

        header = ["TIER", "LOGICAL NAME", "RELATIVE PATH"]
        if parsed.interface:
            header.append("INTERFACE")

        col_widths = [len(h) for h in header]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

        header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(header))
        print(header_line)

        for row in rows:
            row_line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
            print(row_line)


def handle_template_browse(config: dict[str, Any], parsed: argparse.Namespace) -> None:
    """Handle the 'gai template browse' command.

    Provides an interactive browsing interface using fzf to select a template.
    Prints only the selected logical name to stdout, suitable for shell substitution.

    Args:
        config: Effective configuration dictionary
        parsed: Parsed command-line arguments
    """
    import shutil

    from .template_catalog import build_template_catalog

    # Build catalog from configuration
    catalog = build_template_catalog(config)
    records = list(catalog.records)

    # Apply tier filter if specified
    if hasattr(parsed, "tier") and parsed.tier:
        records = [r for r in records if r.tier == parsed.tier]

    # Apply substring filter if specified
    if hasattr(parsed, "filter") and parsed.filter:
        substring = parsed.filter
        records = [r for r in records if substring in r.logical_name_full]

    # Handle empty results
    if not records:
        print("No templates available to browse after applying filters.", file=sys.stderr)
        sys.exit(1)

    # Check if fzf is available
    if not shutil.which("fzf"):
        print("Error: 'fzf' command not found. Please install fzf to use 'gai template browse'.", file=sys.stderr)
        sys.exit(1)

    # Run fzf selection
    selected_record = _run_fzf_selection(records, preview_enabled=not parsed.no_preview)

    if selected_record is None:
        # User cancelled or error occurred
        sys.exit(1)

    # Print only the logical name to stdout
    print(selected_record.logical_name_full)


def handle_template_inspect(config: dict[str, Any], parsed: argparse.Namespace) -> None:
    """Handle the 'gai template inspect' command."""

    interface = build_template_interface(config, parsed.logical_name)

    print(f"Template: {interface.logical_name}\n")

    _print_interface_section("Inputs (I_*, available via CLI flags)", interface.inputs)
    _print_interface_section("Controls (C_*, available via CLI flags)", interface.controls)
    _print_interface_section("Mechanisms (M_*)", interface.mechanisms, show_cli=False)
    _print_outputs_section(interface.outputs)

    if interface.other_variables:
        print("Other variables:")
        for name in sorted(interface.other_variables):
            print(f"  {name}")
    else:
        print("Other variables:\n  (none)")


def _summarize_interface_for_table(interface: TemplateInterface) -> str:
    parts: list[str] = []
    if interface.inputs:
        parts.append("I:" + ", ".join(sorted(filter(None, interface.inputs.values()))))
    if interface.controls:
        parts.append("C:" + ", ".join(sorted(filter(None, interface.controls.values()))))
    if interface.outputs:
        parts.append("O:" + ", ".join(sorted(interface.outputs)))
    if interface.mechanisms:
        parts.append("M:" + ", ".join(sorted(interface.mechanisms)))
    return " | ".join(parts) if parts else "-"


def _print_interface_section(
    title: str,
    prefixed_variables: Mapping[str, str],
    *,
    show_cli: bool = True,
) -> None:
    print(f"{title}:")
    if not prefixed_variables:
        print("  (none)")
        return

    for full_name in sorted(prefixed_variables):
        base_name = prefixed_variables[full_name]
        if show_cli and base_name:
            print(f"  {full_name}  (CLI: --{base_name})")
        else:
            print(f"  {full_name}")


def _print_outputs_section(outputs: set[str]) -> None:
    print("Outputs (O_* tags):")
    if not outputs:
        print("  (none)")
        return

    for name in sorted(outputs):
        print(f"  {name}")


def _run_fzf_selection(
    records: list["TemplateRecord"],
    *,
    preview_enabled: bool,
) -> Optional["TemplateRecord"]:
    """Run fzf to select a template from the list.

    Args:
        records: List of TemplateRecord objects to choose from
        preview_enabled: Whether to show preview pane

    Returns:
        Selected TemplateRecord or None if cancelled/error
    """

    # Build input lines for fzf - use tab-separated format
    # Format: logical_name\ttier\trelative_path\tabsolute_path
    lines = []
    line_to_record: dict[str, TemplateRecord] = {}

    for record in records:
        line = "\t".join(
            [
                record.logical_name_full,
                record.tier,
                record.relative_path.as_posix(),
                str(record.absolute_path),
            ]
        )
        lines.append(line)
        line_to_record[line] = record

    input_text = "\n".join(lines)

    # Build fzf command
    fzf_args = [
        "fzf",
        "--delimiter",
        "\t",
        "--with-nth",
        "1,2,3",  # Show first three columns (logical_name, tier, relative_path)
    ]

    if preview_enabled:
        # Use the 4th field (absolute_path) for preview
        fzf_args.extend(
            [
                "--preview",
                "cat {4}",
                "--preview-window",
                "right:60%:wrap",
            ]
        )

    # Run fzf
    try:
        result = subprocess.run(  # noqa: S603
            fzf_args,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            # Selection made - parse the output line
            selected_line = result.stdout.strip()
            return line_to_record.get(selected_line)
        # Non-zero exit code means cancelled or error
        return None

    except Exception as e:
        print(f"Error running fzf: {e}", file=sys.stderr)
        return None
