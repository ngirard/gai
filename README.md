# gai -- Google Gemini prompting script with flexible CLI, templating, and configuration

[![CI](https://github.com/ngirard/gai/workflows/CI/badge.svg)](https://github.com/ngirard/gai/actions)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

## Rationale
This project provides a robust and flexible command-line interface for interacting with the Google GenAI API. The primary goal is to move beyond static, hardcoded prompts and generation parameters, allowing users to dynamically control the model's input and behavior directly from the shell.

## Installation

### For Users (Recommended)

Install `gai` as a standard Python package using your preferred tool:

```sh
# Using pipx (recommended for CLI tools - installs in isolated environment)
pipx install gai

# Using pip
pip install gai

# Using uv
uv tool install gai

# Once published to PyPI, you can also install directly from Git
pipx install git+https://github.com/ngirard/gai.git
```

After installation, the `gai` command will be available on your PATH:

```sh
gai --help
gai --document @:./report.md --topic "AI" --conf-temperature 0.8
```

### For Development

```sh
# Clone the repository
git clone https://github.com/ngirard/gai.git
cd gai

# Set up the development environment with uv
just setup

# Run the tool in development mode
gai --help
```

## Usage

### Basic Usage
```sh
# Run with template variables
gai --document @:./report.md --topic "Chicken" --conf-temperature 0.8

# Show the rendered prompt without calling the API
gai --document @:./report.md --topic "Seagulls" --show-prompt

# Generate configuration file
gai --generate-config > ~/.config/gai/config.toml
```

### Development Commands
```sh
# Setup development environment
just setup

# Run tests
just test

# Run tests with coverage
just test-cov

# Lint code
just lint

# Format code
just format

# Run all quality checks
just check

# Build wheel and sdist for distribution
just build
```

## Dependencies

The project uses `pyproject.toml` as the single source of truth for dependencies:
- `google-genai>=1.15.0` - Google GenAI API client
- `jinja2>=3.1.0` - Template rendering
- `tomli>=2.0.0; python_version < '3.11'` - TOML parsing for Python < 3.11

## Prerequisites
- Python 3.9+
- `uv` for dependency management (install from https://docs.astral.sh/uv/)
- `just` for task running (optional, but recommended)
- `GOOGLE_API_KEY` environment variable set

## Project Structure

The project follows a modern Python package structure with uv for dependency management:

```
gai/
├── src/gai/              # Main package source
│   ├── __init__.py       # Package initialization
│   ├── __main__.py       # CLI entry point
│   ├── cli.py            # Command-line interface handling
│   ├── config.py         # Configuration management
│   ├── templates.py      # Jinja2 template rendering
│   └── generation.py     # API interaction logic
├── tests/                # Test suite (to be implemented)
├── dev/                  # Development notes and templates
├── .github/workflows/    # CI/CD configuration
├── pyproject.toml        # Project metadata and dependencies
├── ruff.toml             # Linting and formatting config
├── justfile              # Task runner configuration
└── README.md             # This file
```

## Design Decisions

1. Flexible command-line arguments:
    - Problem: Standard `argparse` requires pre-defining every possible
    argument. We need to support arbitrary key-value pairs for prompt
    templating.
    - Solution: Parse the command-line arguments manually.

2. Prompt templating (using Jinja2):
    - Problem: Prompt content needs to be dynamic based on user input and
    potentially include logic (conditionals, loops, filters).
    - Solution: Use Jinja2. This provides a powerful, widely-used templating
    engine capable of complex logic beyond simple variable substitution.
    Variables are passed as a context dictionary.
3. File content loading:
    - Problem: Prompt variables (especially documents) can be large and
    should be loaded from files rather than passed directly on the command line.
    - Solution: Implement a simple convention where a value prefixed with
    `@:` is interpreted as a file path, and its content is read into the
    corresponding variable. This is handled during the argument parsing
    pipeline.
4. Configurable generation parameters:
    - Problem: Model, temperature, response format, etc., should be easily
    adjustable without modifying the code, and persist across sessions.
    - Solution: Introduce a dedicated `--conf-<name> value` syntax for
    configuration parameters. These are parsed separately from template
    variables. Default values are defined in `DEFAULT_CONFIG`.
    Configuration is loaded in layers:
    1. Script defaults (`DEFAULT_CONFIG`).
    2. User configuration file (`~/.config/gai/config.toml`).
    3. Command-line `--conf-` arguments.
    Later layers override earlier ones.
    Systematic type conversion (e.g., float for temperature, int for
    token counts, bool for flags) is applied with error handling.
    Configuration values themselves can also be loaded from files using `@:`.
5. Dynamic Help/Usage information:
    - Problem: Standard `argparse` help doesn't know about our custom
    template variables or `--conf-` parameters.
    - Solution: Manually intercept `--help` and generate usage information
    dynamically. Configuration parameters are listed by inspecting
    `DEFAULT_CONFIG`. **Note:** Automatic listing of template variables
    from Jinja2 templates is complex and has been removed. Users must
    know the variables expected by their templates.
6. Structured logging:
    - Problem: Avoid mixing internal script messages (parsing details, config
    used) with the actual model output (which goes to stdout).
    - Solution: Utilize Python's standard `logging` module. Informational
    and debug messages are directed to stderr via logging, while the model's
    response is printed directly to stdout. A `--debug` flag is added for
    verbose logging.
7. Show rendered prompt:
    - Problem: Users may want to inspect the fully rendered prompt before sending
    it to the API, especially when debugging complex templates.
    - Solution: Implement a `--show-prompt` CLI option that renders both system
    and user instructions with the provided template variables, prints them
    to stdout in a structured format, and exits.

## Distribution and Releases

This project uses wheels as the primary distribution method, making it installable via standard Python package managers.

### For Maintainers

#### Publishing to PyPI

1. Tag a release:
   ```sh
   git tag v0.1.0
   git push origin v0.1.0
   ```

2. The GitHub Actions release workflow will automatically:
   - Build the wheel and source distribution
   - Publish to PyPI (requires PYPI_API_TOKEN secret or trusted publishing setup)
   - Create a GitHub release with the distribution files attached

#### Manual Publishing

```sh
# Build distributions
just build

# Publish to PyPI
just publish

# Or with explicit token
just publish YOUR_PYPI_TOKEN
```

### Version Management

- Version is defined in `pyproject.toml` and `src/gai/__init__.py`
- Keep both synchronized when releasing new versions
- Follow semantic versioning (MAJOR.MINOR.PATCH)
