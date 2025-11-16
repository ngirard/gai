"""Main entry point for gai CLI application."""

import logging
import sys

from .cli import (
    create_parser,
    handle_config_defaults,
    handle_config_edit,
    handle_config_path,
    handle_config_validate,
    handle_config_view,
    handle_template_browse,
    handle_template_inspect,
    handle_template_list,
    parse_args_for_new_cli,
    show_rendered_prompt,
)
from .config import CONFIG_FILE_DIR, load_effective_config
from .exceptions import CliUsageError, ConfigError, GaiError, GenerationError, TemplateError
from .generation import generate


def _has_cli_override(args_list: list[str], name: str) -> bool:
    flag = f"--conf-{name}"
    return flag in args_list


def _apply_user_template_override(args_list: list[str], template_name: str | None) -> list[str]:
    if not template_name:
        return args_list

    if _has_cli_override(args_list, "user-instruction-template"):
        return args_list

    return [*args_list, "--conf-user-instruction-template", template_name]


def _handle_new_cli(args_list: list[str]) -> None:
    """Handle new CLI invocation (subcommand-based)."""
    logger = logging.getLogger(__name__)

    parser = create_parser()

    # Handle the special case of no subcommand - show help
    if not args_list or args_list[0] in ["-h", "--help"]:
        parser.print_help()
        sys.exit(0)

    # Parse arguments
    try:
        parsed, template_vars = parse_args_for_new_cli(args_list)
    except SystemExit:
        # argparse called sys.exit (e.g., for --help)
        raise
    except Exception as e:
        logger.error(f"Argument parsing error: {e}")
        sys.exit(1)

    # Set debug logging if requested
    if parsed.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    # Handle commands
    if parsed.command == "config":
        # Config subcommands
        if parsed.config_command == "view":
            # Load config and display
            effective_config = load_effective_config(args_list)
            handle_config_view(effective_config)
        elif parsed.config_command == "edit":
            handle_config_edit()
        elif parsed.config_command == "validate":
            handle_config_validate(getattr(parsed, "file", None))
        elif parsed.config_command == "defaults":
            handle_config_defaults()
        elif parsed.config_command == "path":
            handle_config_path()
        else:
            # No subcommand provided for config
            parser.parse_args(["config", "-h"])

    elif parsed.command == "template":
        # Template subcommands
        if parsed.template_command == "render":
            template_override = getattr(parsed, "template", None) or getattr(parsed, "template_name", None)
            config_args = _apply_user_template_override(args_list, template_override)
            # Load config
            effective_config = load_effective_config(config_args)

            # Determine which part to render
            part = None
            if hasattr(parsed, "part"):
                if parsed.part == "user":
                    part = "user"
                elif parsed.part == "system":
                    part = "system"
                # "both" or default is None (renders both)

            show_rendered_prompt(effective_config, template_vars, part)
        elif parsed.template_command == "list":
            # Load config and handle template list
            effective_config = load_effective_config(args_list)
            handle_template_list(effective_config, parsed)
        elif parsed.template_command == "browse":
            # Load config and handle template browse
            effective_config = load_effective_config(args_list)
            handle_template_browse(effective_config, parsed)
        elif parsed.template_command == "inspect":
            effective_config = load_effective_config(args_list)
            handle_template_inspect(effective_config, parsed)
        else:
            # No subcommand provided for template
            parser.parse_args(["template", "-h"])

    elif parsed.command == "generate":
        # Generate command
        effective_config = load_effective_config(args_list)

        if parsed.output_file and not parsed.capture_tag:
            raise CliUsageError("--output-file requires --capture-tag")

        if parsed.show_prompt:
            show_rendered_prompt(effective_config, template_vars)
        else:
            generate(
                effective_config,
                template_vars,
                capture_tag=getattr(parsed, "capture_tag", None),
                output_file=getattr(parsed, "output_file", None),
            )

    else:
        # No command provided: show top-level help and exit with error
        logger.error("No command provided. Use one of: generate, config, template.")
        parser.print_help()
        sys.exit(1)


def main() -> None:
    """Main execution function."""
    # Configure logging once, early in the process
    log_level = logging.DEBUG if "--debug" in sys.argv else logging.WARNING
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stderr)

    logger = logging.getLogger(__name__)

    # Ensure config directory exists
    try:
        CONFIG_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning(f"Could not create config directory {CONFIG_FILE_DIR}: {e}")

    args_list = list(sys.argv[1:])

    try:
        _handle_new_cli(args_list)

    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except TemplateError as e:
        logger.error(f"Template error: {e}")
        sys.exit(1)
    except CliUsageError as e:
        logger.error(f"Usage error: {e}")
        sys.exit(1)
    except GenerationError as e:
        logger.error(f"Generation error: {e}")
        sys.exit(1)
    except GaiError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception:
        logger.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
