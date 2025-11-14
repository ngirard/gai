# justfile for a Python project managed with uv
#
# This file provides a set of commands to streamline common development tasks
# using `uv`.

# --- Settings and Variables ---

# Use bash with strict error handling for script robustness.
#set shell := ["bash", "-euo", "pipefail"]

# Automatically load variables from a .env file in the project root, if it exists.
set dotenv-load := true

# Set the 'default' recipe to run when 'just' is called without arguments.
#set default := 'default'

# Default Python version for tasks like `python-install` if no version is specified.
# `uv` commands like `sync` and `run` will primarily respect `.python-version`
# or `pyproject.toml`'s `project.requires-python`.
DEFAULT_PYTHON_VERSION := "3.11"

# --- Help and Default Task ---

export HELP := '''
Project Justfile Help

This file provides a set of commands to streamline common development tasks using `uv`.

To see all available commands:
  just --list

To run a specific command:
  just <command_name> [arguments...]

--- Core Development Workflow ---

setup:
    Setup the project: create/update virtual environment and install all dependencies.
    This is a good first command to run after cloning or for a clean setup.
    Installs main dependencies, all optional extras, and development dependencies.

lock:
    Explicitly generate or update the uv.lock file based on pyproject.toml.

sync:
    Explicitly synchronize the virtual environment from uv.lock.
    Useful after pulling changes that might have updated uv.lock.

add <dep>:
    Add a runtime dependency to pyproject.toml and update lockfile/environment.
    Usage: just add requests
    Usage: just add "django>=4.0,<5.0"

add-dev <dep>:
    Add a development dependency to pyproject.toml (in [dependency-groups].dev).
    Usage: just add-dev pytest
    Usage: just add-dev "ruff==0.2.0"

add-optional <extra> <dep>:
    Add an optional dependency to a specific extra group in pyproject.toml.
    Usage: just add-optional plotting matplotlib

remove <dep>:
    Remove a dependency from pyproject.toml (uv auto-detects its group).
    Usage: just remove requests

update-all:
    Upgrade all dependencies in uv.lock to their latest compatible versions.
    Then, re-sync the environment.

update-package <package>:
    Upgrade a specific package in uv.lock to its latest compatible version.
    Then, re-sync the environment.
    Usage: just update-package requests

--- Running and Testing ---

run <cmd...>:
    Run an arbitrary command or script within the project's managed environment.
    `uv run` automatically ensures the environment is locked and synced.
    Usage: just run python myscript.py
    Usage: just run my_cli_tool --version (if defined in [project.scripts])

test:
    Run tests using pytest.
    Ensures pytest is added as a dev dependency if not already present.
    Adjust `tests/` path if your tests are elsewhere.

lint:
    Lint the project using Ruff.
    Ensures ruff is added as a dev dependency.

format:
    Format the project's code using Ruff.
    Ensures ruff is added as a dev dependency.

tree:
    Display the project's resolved dependency tree from uv.lock.

--- Building and Distribution ---

build:
    Build source distribution (sdist) and wheel for the project.
    Artifacts are placed in the `dist/` directory.

build-release:
    Build sdist and wheel for release, ensuring no `tool.uv.sources` are used.
    This simulates how the package would be built by others or in CI.

publish [token='']:
    Publish the package to PyPI or a configured alternative index.
    Assumes distributions have been built (e.g., via `just build`).
    For PyPI, prefer trusted publishing. For manual, use UV_PUBLISH_TOKEN env var
    or pass token as an argument (less secure).
    Usage: just publish
    Usage: just publish YOUR_PYPI_TOKEN_HERE

clean:
    Clean build artifacts, Python cache files.
    Optionally, uncomment lines to remove .venv and uv.lock for a full reset.

--- Python Version Management (using `uv python`) ---

python-install [version=DEFAULT_PYTHON_VERSION]:
    Install a specific Python version using uv's managed toolchain.
    `uv` will download it if not already installed by `uv`.
    Usage: just python-install          (uses DEFAULT_PYTHON_VERSION)
    Usage: just python-install 3.12

python-pin [version=DEFAULT_PYTHON_VERSION]:
    Pin the project's Python version by creating/updating .python-version file.
    This version will be preferred by `uv` for project operations.
    Usage: just python-pin              (uses DEFAULT_PYTHON_VERSION)
    Usage: just python-pin 3.12

python-list:
    List uv-managed and other discovered Python versions.

--- Cache Management ---

cache-clean:
    Clean the entire global uv cache (use with caution, will slow down next operations).

cache-prune:
    Prune unused or outdated entries from the global uv cache. Safe to run periodically.

cache-prune-ci:
    Prune the global uv cache, optimized for CI environments.
    Removes downloaded pre-built wheels but retains wheels built from source.

--- CI Related Tasks ---

check-lock:
    Check if the uv.lock file is up-to-date with pyproject.toml.
    This command will exit with an error if the lockfile needs regeneration.
    Useful in CI to ensure committed lockfile is current.

check-run-lint:
    Example of running a command (like linting) ensuring the lockfile is not modified.
    Useful in CI to verify that an operation doesn't unexpectedly try to change the lockfile.

--- Advanced / Optional ---

export-reqs [output_file="requirements.txt"]:
    Export the current project's lockfile to a requirements.txt format.
    Usage: just export-reqs
    Usage: just export-reqs requirements_prod.txt

# test-lowest:
#     Placeholder for testing with lowest direct dependency versions (primarily for libraries).
#     `uv lock` does not directly support resolution strategies like `lowest-direct`.
#     This typically involves `uv pip compile --resolution lowest-direct ...` and a separate sync.
#     Example steps (conceptual):
#     uv pip compile pyproject.toml --resolution lowest-direct -o requirements-lowest.txt
#     uv pip sync requirements-lowest.txt
#     uv run pytest tests/
#     rm requirements-lowest.txt # cleanup
''' #'

# The default task: Displays comprehensive help information.
default:
    @printf '%s\n' "$HELP"


# Alias to show all available tasks.
@list:
    @just --list

# --- Core Development Workflow ---

# Setup the project environment and sync dependencies.
setup:
    @echo "⚙️  Setting up project environment and syncing dependencies..."
    uv sync --all-extras --dev

# Explicitly generate or update the uv.lock file.
lock:
    @echo "🔒 Locking dependencies..."
    uv lock

# Explicitly synchronize the virtual environment from uv.lock.
sync:
    @echo "🔄 Syncing environment from uv.lock..."
    uv sync --all-extras --dev

# Add a runtime dependency.
add dep:
    @echo "➕ Adding runtime dependency: {{dep}}"
    uv add "{{dep}}"

# Add a development dependency.
add-dev dep:
    @echo "➕ Adding development dependency: {{dep}}"
    uv add --dev "{{dep}}"

# Add an optional dependency to an extra group.
add-optional extra dep:
    @echo "➕ Adding optional dependency '{{dep}}' to extra group '{{extra}}'"
    uv add --optional "{{extra}}" "{{dep}}"

# Remove a dependency.
remove dep:
    @echo "➖ Removing dependency: {{dep}}"
    uv remove "{{dep}}"

# Upgrade all dependencies.
update-all:
    @echo "⬆️  Upgrading all dependencies in uv.lock..."
    uv lock --upgrade
    uv sync --all-extras --dev

# Upgrade a specific package.
update-package package:
    @echo "⬆️  Upgrading package '{{package}}' in uv.lock..."
    uv lock --upgrade-package "{{package}}"
    uv sync --all-extras --dev


# --- Running and Testing ---

# Run a command in the project environment.
run *args:
    @echo "🚀 Running command with uv: {{args}}"
    uv run {{args}}

# Run the gai CLI tool with arguments
gai *args:
    @echo "🤖 Running gai..."
    uv run gai {{args}}

# Run tests using pytest.
test:
    uv add --dev pytest # Idempotent: ensures pytest is a dev dependency
    @echo "🧪 Running tests with pytest..."
    uv run pytest tests/

# Run tests with coverage
test-cov:
    uv add --dev pytest pytest-cov # Ensure test dependencies
    @echo "🧪 Running tests with coverage..."
    uv run pytest --cov=gai --cov-report=term-missing --cov-report=html tests/

# Lint the project using Ruff.
lint:
    uv add --dev ruff # Idempotent: ensures ruff is a dev dependency
    @echo "🔍 Linting with Ruff..."
    uv run ruff check .

# Fix linting issues automatically
lint-fix:
    uv add --dev ruff
    @echo "🔧 Fixing linting issues with Ruff..."
    uv run ruff check --fix .

# Format the project's code using Ruff.
format:
    uv add --dev ruff # Idempotent: ensures ruff is a dev dependency
    @echo "🎨 Formatting with Ruff..."
    uv run ruff format .

# Check formatting without making changes
format-check:
    uv add --dev ruff
    @echo "🎨 Checking formatting with Ruff..."
    uv run ruff format --check .

# Run all quality checks (format check, lint)
check: format-check lint
    @echo "✅ All quality checks passed!"

# Display the project's dependency tree.
tree:
    @echo "🌳 Project dependency tree:"
    uv tree


# --- Building and Distribution ---

# Build standalone gai.py script from modular sources
build-script:
    @echo "🔨 Building standalone gai.py from modular sources..."
    uv run python build_script.py

# Build source distribution (sdist) and wheel.
build:
    @echo "📦 Building project (sdist and wheel)..."
    uv build

# Build sdist and wheel for release (--no-sources).
build-release:
    @echo "📦 Building project for release (sdist and wheel, --no-sources)..."
    uv build --no-sources

# Publish the package.
publish token='':
    @echo "🚀 Publishing package..."
    if [[ -n "{{token}}" ]]; then \
        uv publish --token "{{token}}"; \
    else \
        uv publish; \
    fi

# Clean build artifacts and cache files.
clean:
    @echo "🧹 Cleaning build artifacts and Python cache files..."
    rm -rf dist/ build/ *.egg-info/
    find . -type d -name '__pycache__' -exec rm -rf {} +
    find . -type f -name '*.pyc' -delete
    find . -type f -name '*.pyo' -delete
    # For a deeper clean (use with caution):
    # @echo "🧹 Optionally removing .venv and uv.lock..."
    # rm -rf .venv/
    # rm -f uv.lock


# --- Python Version Management (using `uv python`) ---

# Install a specific Python version via uv.
python-install version=DEFAULT_PYTHON_VERSION:
    @echo "🐍 Ensuring Python {{version}} is installed via uv..."
    uv python install "{{version}}"

# Pin the project's Python version.
python-pin version=DEFAULT_PYTHON_VERSION:
    @echo "📌 Pinning project's .python-version to {{version}}..."
    uv python pin "{{version}}"

# List uv-managed and other discovered Python versions.
python-list:
    @echo "🐍 Available and installed Python versions known to uv:"
    uv python list


# --- Cache Management ---

# Clean the entire global uv cache.
cache-clean:
    @echo "🗑️  Cleaning the entire uv cache..."
    uv cache clean

# Prune unused or outdated entries from the global uv cache.
cache-prune:
    @echo "✂️  Pruning the uv cache..."
    uv cache prune

# Prune the global uv cache for CI.
cache-prune-ci:
    @echo "✂️  Pruning the uv cache for CI..."
    uv cache prune --ci


# --- CI Related Tasks ---

# Check if the uv.lock file is up-to-date.
check-lock:
    @echo "🔎 Checking if uv.lock is up-to-date..."
    uv lock --check

# Run linter with --locked flag.
check-run-lint:
    uv add --dev ruff # Ensure ruff is a dev dependency
    @echo "🔎 Running linter with --locked flag (no lockfile updates allowed)..."
    uv run --locked ruff check .


# --- Advanced / Optional ---

# Export lockfile contents to requirements.txt.
export-reqs output_file="requirements.txt":
    @echo "📄 Exporting lockfile contents to {{output_file}}..."
    uv export --output-file "{{output_file}}"

# test-lowest:
#     Placeholder for testing with lowest direct dependency versions.
#     uv lock does not directly support this; requires a different approach.
#     # Example steps (conceptual):
#     # uv pip compile pyproject.toml --resolution lowest-direct -o requirements-lowest.txt
#     # uv pip sync requirements-lowest.txt
#     # uv run pytest tests/
#     # rm requirements-lowest.txt # cleanup