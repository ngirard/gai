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
# View help
gai --help

# Generate content
gai generate --document @:./report.md --topic "AI" --conf-temperature 0.8

# Manage configuration
gai config view
gai config edit
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

### Quick Start

```sh
# Generate content with template variables
gai generate --document @:./report.md --topic "Chicken" --conf-temperature 0.8

# Show the rendered prompt without calling the API
gai generate --show-prompt --document @:./report.md --topic "Seagulls"

# View effective configuration
gai config view

# Generate default configuration file
gai config defaults > ~/.config/gai/config.toml
# Or keep one with your repository
gai config defaults > .gai/config.toml
```

### CLI Structure

The CLI is organized into logical subcommands for different operations:

#### Generate Content (`gai generate`)

The primary command for generating content with the Gemini API:

```sh
# Basic generation
gai generate --document @:./report.md --input "Summarize this"

# Preview the prompt before sending
gai generate --show-prompt --document @:./file.txt

# Override config parameters
gai generate --conf-temperature 0.8 --conf-model gemini-pro --document "Text"
```

#### Configuration Management (`gai config`)

Manage your configuration settings:

```sh
# View effective configuration (defaults → user file → repo file → CLI)
gai config view

# Open config file in $EDITOR
gai config edit

# Validate configuration file syntax
gai config validate
gai config validate --file /path/to/config.toml

# Print default configuration
gai config defaults

# Show configuration file path
gai config path
```

#### Template Rendering (`gai template render`)

Debug and preview template rendering:

```sh
# Render complete prompt (system + user instructions)
gai template render --document @:./file.txt --input "Query"

# Render only user instruction
gai template render --part user --document "Content"

# Render only system instruction
gai template render --part system --conf-system-instruction "You are helpful"
```

## Template System

`gai` includes a powerful template system for organizing and composing prompts using Jinja2 with Obsidian-style logical names.

### Key Features

- **Organized structure**: Templates are organized in configurable directories with tier-based precedence
- **Logical names**: Use extensionless names like `"summary"` or `"layout/base_conversation"` instead of file paths
- **Template composition**: Use `{% extends %}`, `{% include %}`, and `{% import %}` for reusable components
- **Strict correctness**: Ambiguous template names cause errors rather than silently auto-resolving
- **Project and user templates**: Override user-level templates with project-specific ones

### Quick Start

1. **Create template directories:**
```sh
# Project templates (highest precedence)
mkdir -p .gai/templates

# User templates (global defaults)
mkdir -p ~/.config/gai/templates
```

2. **Create a template file** (`.gai/templates/prompts/summarize.j2`):
```jinja2
{% extends "layout/base_conversation" %}

{% block task %}
Please summarize the following document:

{{ document }}

Focus on key findings and conclusions.
{% endblock %}
```

3. **Configure named templates** (`.gai/config.toml` or `~/.config/gai/config.toml`):
```toml
# Template root directories
project-template-paths = [".gai/templates"]
user-template-paths = ["~/.config/gai/templates"]

# Named template references (use logical names without extensions)
user-instruction-template = "prompts/summarize"
system-instruction-template = "system/expert_analyst"
```

4. **Use templates:**
```sh
# Generate using the configured template
gai generate --document @:report.txt --role "analyst"

# Override template for one-off use
gai generate --conf-user-instruction-template "prompts/explain" --document "complex topic"

# Preview rendered template
gai template render --document "test content"
```

### Template Tiers and Precedence

Templates are organized in three tiers with precedence order:

1. **`project`** (highest): `.gai/templates` in your repository
2. **`user`** (medium): `~/.config/gai/templates` for personal defaults
3. **`builtin`** (lowest): Templates shipped with `gai`

When resolving a template name like `"summary"`:
- Search project tier first
- If not found, search user tier
- If not found, search builtin tier
- If multiple matches in the same tier: **error** (ambiguity must be resolved)

### Logical Names vs Physical Files

Templates are referenced by **logical names** (extensionless):

```
Physical file:    .gai/templates/layout/base_conversation.j2
Logical name:     layout/base_conversation

Physical file:    .gai/templates/summary.j2
Logical name:     summary
```

Use logical names in:
- Configuration: `user-instruction-template = "prompts/summarize"`
- Template tags: `{% extends "layout/base_conversation" %}`
- CLI overrides: `--conf-user-instruction-template "prompts/analyze"`

### Template Composition

Build complex prompts from reusable components:

```jinja2
{# Base layout template #}
{% extends "layout/base_conversation" %}

{% block task %}
Analyze this document for {{ aspect }}:
{{ document }}
{% endblock %}

{# Include reusable snippets #}
{% include "partials/output_format" %}

{# Import and use macros #}
{% import "macros/formatting" as fmt %}
{{ fmt.section("Results", analysis) }}
```

### Configuration Reference

```toml
# Template root directories (list of paths)
project-template-paths = [".gai/templates"]        # Project-specific
user-template-paths = ["~/.config/gai/templates"]  # User defaults
builtin-template-paths = []                        # Built-in (optional)

# Named template references (logical names without extensions)
system-instruction-template = "system/expert"      # Use named template
user-instruction-template = "prompts/summarize"    # Use named template

# Legacy literal templates (lower precedence - only used if *-template not set)
system-instruction = "You are an expert."          # Literal string
user-instruction = "Summarize: {{ document }}"     # Literal string
```

### Precedence Rules

For system and user instructions:

1. If `*-instruction-template` is set → Use named template from catalog
2. Otherwise → Fall back to `*-instruction` (literal string or `@:file`)

This ensures named templates take precedence when both are configured.

### Avoiding Ambiguity

The template system enforces strict resolution to avoid surprises:

**✅ Good - Unique names:**
```
.gai/templates/
  ├── summarize.j2
  └── analyze.j2
```

**⚠️ Risky - Same basename (requires path-specific names):**
```
.gai/templates/
  ├── summary.j2          # Resolve as "summary"
  └── email/
      └── summary.j2       # Resolve as "email/summary"
```

**❌ Error - Multiple extensions for same base name:**
```
.gai/templates/
  ├── summary.j2          # Ambiguous!
  └── summary.j2.md       # Ambiguous!
```

Use either explicit extensions (`"summary.j2"`) or keep only one file.

### Best Practices

- **Organize by purpose**: Use subdirectories like `layout/`, `prompts/`, `partials/`, `macros/`
- **Use descriptive names**: `analyze_financial_report.j2` instead of `report.j2`
- **Document variables**: Add comments explaining required template variables
- **Provide defaults**: Use `{{ var | default("value") }}` for optional variables
- **Commit templates**: Add `.gai/templates/` to version control
- **Override strategically**: Keep generic templates in user tier, project-specific in project tier

### For More Information

See the comprehensive [Template System Documentation](docs/templates.md) for:

- Detailed configuration options
- Template composition examples
- Resolution algorithm details
- Troubleshooting guide
- Future CLI commands (`gai template list`, `gai template browse`)

### Backward Compatibility

All legacy command-line invocations continue to work:

```sh
# Legacy style (still supported)
gai --document @:./report.md --topic "Chicken" --conf-temperature 0.8
gai --show-prompt --document @:./report.md
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

1. **Multi-level CLI with subcommands**:
    - **Problem**: A flat CLI with many flags becomes hard to discover and organize as features grow.
    - **Solution**: Restructured the CLI into logical subcommands (`generate`, `config`, `template`) that mirror the codebase structure. Uses argparse for robust subcommand parsing while maintaining full backward compatibility with the legacy flat options style.
    - **Design principles**:
        - Verb-noun structure (e.g., `config view`, `template render`)
        - Subcommands reflect code modules (`config.py` → `config` subcommand)
        - Short, predictable names for discoverability
        - Easy to extend with new capabilities

2. Flexible command-line arguments:
    - Problem: Standard `argparse` requires pre-defining every possible
    argument. We need to support arbitrary key-value pairs for prompt
    templating.
    - Solution: Parse template variables using `parse_known_args` to handle
    arbitrary `--name value` pairs that aren't pre-defined configuration options.

3. Prompt templating (using Jinja2):
    - Problem: Prompt content needs to be dynamic based on user input and
    potentially include logic (conditionals, loops, filters).
    - Solution: Use Jinja2. This provides a powerful, widely-used templating
    engine capable of complex logic beyond simple variable substitution.
    Variables are passed as a context dictionary.

4. File content loading:
    - Problem: Prompt variables (especially documents) can be large and
    should be loaded from files rather than passed directly on the command line.
    - Solution: Implement a simple convention where a value prefixed with
    `@:` is interpreted as a file path, and its content is read into the
    corresponding variable. This is handled during the argument parsing
    pipeline.

5. Configurable generation parameters:
    - Problem: Model, temperature, response format, etc., should be easily
    adjustable without modifying the code, and persist across sessions.
    - Solution: Introduce a dedicated `--conf-<name> value` syntax for
    configuration parameters. These are parsed separately from template
    variables. Default values are defined in `DEFAULT_CONFIG`.
    Configuration is loaded in layers:
    1. Script defaults (`DEFAULT_CONFIG`).
    2. User configuration file (`~/.config/gai/config.toml`).
    3. Repository configuration file (`<repo>/.gai/config.toml`, detected from the nearest Git root).
    4. Command-line `--conf-` arguments.
    Later layers override earlier ones.
    Systematic type conversion (e.g., float for temperature, int for
    token counts, bool for flags) is applied with error handling.
    Configuration values themselves can also be loaded from files using `@:`.

6. Structured logging:
    - Problem: Avoid mixing internal script messages (parsing details, config
    used) with the actual model output (which goes to stdout).
    - Solution: Utilize Python's standard `logging` module. Informational
    and debug messages are directed to stderr via logging, while the model's
    response is printed directly to stdout. A `--debug` flag is added for
    verbose logging.

7. Template rendering and preview:
    - Problem: Users may want to inspect the fully rendered prompt before sending
    it to the API, especially when debugging complex templates.
    - Solution: Implement `gai template render` command (and `gai generate --show-prompt`
    for backward compatibility) that renders system and user instructions with the
    provided template variables, prints them to stdout in a structured format,
    and exits. Supports rendering specific parts (`--part user` or `--part system`)
    for targeted debugging.

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
