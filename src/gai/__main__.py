"""Main entry point for gai CLI application."""

import logging
import sys

from .cli import parse_template_args, show_rendered_prompt, usage
from .config import CONFIG_FILE_DIR, load_effective_config
from .exceptions import CliUsageError, ConfigError, GaiError, GenerationError, TemplateError
from .generation import generate


def _handle_generate_config() -> None:
    """Handle the --generate-config flag."""
    import tomli_w

    from .config import DEFAULT_CONFIG

    # Filter out None values for TOML serialization
    config_to_dump = {k: v for k, v in DEFAULT_CONFIG.items() if v is not None}

    print("# Default configuration for gai script")
    print("# This file is loaded from ~/.config/gai/config.toml")
    print()
    print(tomli_w.dumps(config_to_dump))


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

    # Handle --generate-config early
    if "--generate-config" in args_list:
        _handle_generate_config()
        sys.exit(0)

    try:
        # Load effective config
        effective_config = load_effective_config(args_list)

        # Handle --help
        if "-h" in args_list or "--help" in args_list:
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
