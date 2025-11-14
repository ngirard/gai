"""Main entry point for gai CLI application."""

import logging
import sys

from .cli import parse_template_args, show_rendered_prompt, usage
from .config import CONFIG_FILE_DIR, load_effective_config
from .generation import generate


def main() -> None:
    """Main execution function."""
    # Configure basic logging early
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stderr)

    # Ensure config directory exists
    try:
        CONFIG_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logging.getLogger(__name__).warning(f"Could not create config directory {CONFIG_FILE_DIR}: {e}")

    args_list = list(sys.argv[1:])

    # Handle --generate-config early
    if "--generate-config" in args_list:
        import toml

        from .config import DEFAULT_CONFIG

        print("# Default configuration for gai script")
        print("# This file is loaded from ~/.config/gai/config.toml")
        print()
        print(toml.dumps(DEFAULT_CONFIG))
        sys.exit(0)

    # Load effective config
    try:
        effective_config = load_effective_config(args_list)
    except Exception:
        sys.exit(1)

    # Handle --help
    if "-h" in args_list or "--help" in args_list:
        usage(effective_config)
        sys.exit(0)

    # Parse template arguments
    template_vars = parse_template_args(args_list)

    # Handle --show-prompt
    if "--show-prompt" in args_list:
        log_level = logging.DEBUG if "--debug" in args_list else logging.INFO
        logging.basicConfig(
            level=log_level, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stderr, force=True
        )
        show_rendered_prompt(effective_config, template_vars)
        sys.exit(0)

    # Set logging level for normal execution
    log_level = logging.DEBUG if "--debug" in args_list else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stderr, force=True
    )

    # Run generation
    generate(effective_config, template_vars)


if __name__ == "__main__":
    main()
