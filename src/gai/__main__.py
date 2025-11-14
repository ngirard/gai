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
    parse_args_for_new_cli,
    parse_template_args,
    show_rendered_prompt,
    usage,
)
from .config import CONFIG_FILE_DIR, load_effective_config
from .exceptions import CliUsageError, ConfigError, GaiError, GenerationError, TemplateError
from .generation import generate


def _is_legacy_invocation(args: list[str]) -> bool:
    """Check if this is a legacy-style invocation (no subcommand)."""
    # Legacy invocations don't start with a known subcommand
    if not args:
        return True

    first_arg = args[0]

    # If first arg is a flag, it's legacy
    if first_arg.startswith("-"):
        return True

    # If first arg is a known subcommand, it's new style
    # Otherwise, it's legacy (could be a template var like --document)
    return first_arg not in ["generate", "config", "template"]


def _handle_legacy_cli(args_list: list[str]) -> None:
    """Handle legacy CLI invocation (backward compatibility)."""
    logging.getLogger(__name__)

    # Handle --generate-config early
    if "--generate-config" in args_list:
        handle_config_defaults()
        sys.exit(0)

    # Load effective config
    effective_config = load_effective_config(args_list)

    # Handle --help
    if not args_list or "-h" in args_list or "--help" in args_list:
        usage(effective_config)
        sys.exit(0)

    # Parse template arguments
    template_vars = parse_template_args(args_list)

    # Handle --show-prompt
    if "--show-prompt" in args_list:
        # Adjust logging level if needed
        if "--debug" in args_list:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)
        show_rendered_prompt(effective_config, template_vars)
        sys.exit(0)

    # Adjust logging level for normal execution
    if "--debug" in args_list:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    # Run generation
    generate(effective_config, template_vars)


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
            # Load config
            effective_config = load_effective_config(args_list)

            # Determine which part to render
            part = None
            if hasattr(parsed, "part"):
                if parsed.part == "user":
                    part = "user"
                elif parsed.part == "system":
                    part = "system"
                # "both" or default is None (renders both)

            show_rendered_prompt(effective_config, template_vars, part)
        else:
            # No subcommand provided for template
            parser.parse_args(["template", "-h"])

    elif parsed.command == "generate":
        # Generate command
        effective_config = load_effective_config(args_list)

        if parsed.show_prompt:
            show_rendered_prompt(effective_config, template_vars)
        else:
            generate(effective_config, template_vars)

    else:
        # No command provided - default to generate for backward compatibility
        _handle_legacy_cli(args_list)


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
        # Determine if this is legacy or new CLI invocation
        if _is_legacy_invocation(args_list):
            _handle_legacy_cli(args_list)
        else:
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
