# Strategy for implementing `gai template list` and `gai template browse`

This document describes how to implement the `gai template list` and `gai template browse` commands in a way that is friendly to both human maintainers and LLM agents acting as code contributors.

The goals are:

* To make template discovery and selection first class, using the existing catalog and resolution mechanisms.
* To provide a clear, testable separation of concerns so that behavior is easy to extend.
* To ensure the implementation is thoroughly discoverable in documentation and CLI help.
* To give enough context that an LLM can meaningfully implement the feature without additional external docs.
* To enforce that tests and production code remain physically separated (no test snippets in `src/gai`).

Throughout this document, “you” refers to the implementer (whether human or LLM).

---

## Current situation and pain points

### What exists today

Key pieces already implemented:

* **Configuration and roots**

  * `src/gai/config.py` defines:

    * `DEFAULT_CONFIG`, including template-related keys such as:

      * `project-template-paths`
      * `user-template-paths`
      * `builtin-template-paths`
      * `system-instruction-template`
      * `user-instruction-template`
    * `get_template_roots(config)` resolves configured paths into a dict:

      * `{"project": [...], "user": [...], "builtin": [...]}`

* **Template catalog and discovery**

  * `src/gai/template_catalog.py` defines:

    * `TemplateRecord` dataclass, capturing:

      * `logical_name_full` (e.g. `"layout/base_conversation"`)
      * `relative_path`
      * `absolute_path`
      * `tier` (`"project"`, `"user"`, `"builtin"`)
      * `root_index`
      * `extension`
    * `discover_templates(project_roots, user_roots, builtin_roots, ...) -> list[TemplateRecord]`
    * `TemplateCatalog` wrapper:

      * `filter_by_tier`
      * `get_all_logical_names`
      * iteration support
    * Tier precedence constants and extension detection.

* **Template resolution and rendering**

  * `src/gai/templates.py`:

    * `resolve_template_name(catalog, logical_name, ...) -> TemplateRecord`

      * tier-aware, ambiguity-aware resolution.
    * `CatalogLoader` and `create_jinja_env_from_catalog(...)` for Jinja that uses the catalog.
    * `render_system_instruction(config, template_vars)`
    * `render_user_instruction(config, template_vars)`
    * These already build a catalog via `get_template_roots` + `discover_templates`.

* **CLI skeleton**

  * `src/gai/cli.py` defines the subcommand structure:

    * Root parser with `--debug` and subcommands:

      * `generate`
      * `config`
      * `template`
    * Under `template`, only `render` exists today:

      * `gai template render [--part both|user|system] ...`
    * `parse_args_for_new_cli` / `parse_template_args_from_list` handle config flags and template variables.
  * `src/gai/__main__.py` routes:

    * Legacy invocations (no subcommand) to `_handle_legacy_cli`.
    * New-style invocations (subcommands) to `_handle_new_cli`, which then dispatches `command == "template"` to logic that handles only `template_command == "render"`.

* **Documentation**

  * `docs/templates.md` is thorough and already describes:

    * The catalog concept, tiers, and resolution algorithm.
    * Future CLI commands `gai template list` and `gai template browse` as “planned”.
  * `README.md` references the template system and points to `docs/templates.md`.

### Pain points

1. **No actual `template list` or `template browse` implementation**
   The docs describe future commands, but the user cannot run them. This breaks expectations and hinders template discoverability.

2. **Template discoverability**

   * Users currently cannot:

     * List all templates known to the catalog.
     * See which tier a template comes from.
     * Browse interactively with a preview.

3. **Mental model vs reality**

   * The documentation claims the CLI will reuse the same catalog and resolution logic.
   * The code actually already has a catalog and resolution, but the CLI does not expose it.

4. **Preview flag mismatch**

   * `docs/templates.md` currently suggests:

     ```bash
     gai template browse --preview
     ```
   * The new requirement is:

     * Preview should be **on by default**.
     * `--preview` is misleading (and should either be removed or turned into `--no-preview` if we want a switch).
   * This mismatch must be explicitly corrected in code and docs.

5. **No clear contract for non-interactive use**

   * There is no “stable machine output” for tools or scripts (including LLMs using `gai` as a subcommand), e.g. JSON output for `template list`, or a deterministic return format for `template browse`.

---

## High level goals and constraints

### Functional goals

1. **Implement `gai template list`**

   * List all templates known to the catalog, in catalog order.
   * Show at least:

     * Logical name (canonical name used for resolution).
     * Tier (`project`, `user`, `builtin`).
     * Relative path within the tier root.
   * Provide a JSON output mode for machine consumption.

2. **Implement `gai template browse`**

   * Provide an interactive selection interface over the same catalog.
   * Preview must be displayed **by default**.
   * The command should:

     * Print only the selected **logical name** to stdout by default, so that it can be used in command substitution like:

       ```bash
       gai config set user-instruction-template "$(gai template browse)"
       ```
     * Use stderr for prompts, messages, and errors.
   * Use `fzf` or similar as the primary selector, but be robust to its absence.

3. **Reuse the existing catalog as a single source of truth**

   * Both commands must build their view from:

     * `get_template_roots(config)`
     * `discover_templates(...)`
     * optionally wrapped in `TemplateCatalog`.

4. **Support filtering** (at least in `list`)

   * Filter by tier (`--tier project|user|builtin`).
   * Filter by logical name substring or pattern (`--filter`).

5. **Respect configuration layering**

   * Use the same effective configuration that other commands use:

     * Defaults → user config → repo config → CLI `--conf-*`.

### Non-functional goals and constraints

1. **Separate tests from code**

   * **Never** add test code or example test harnesses into `src/gai`.
   * All tests must live under `tests/` (for example `tests/test_template_list.py`, `tests/test_template_browse.py`).
   * If you need helper functions to make testing easier, put them in `src/gai` as reusable, non-test-specific utilities, and test them from the `tests/` tree.

2. **Backwards compatibility**

   * The legacy CLI should remain unaffected.
   * Existing commands (`generate`, `config`, `template render`) must keep their current behavior.

3. **Consistent logging and error handling**

   * Use `logging` for debug/info messages (to stderr).
   * Do not mix structured output (list or selection results) with logging on stdout.
   * Use the existing exception types (`CliUsageError`, `TemplateError`, etc.) when appropriate.

4. **Documentation and help must be updated**

   * Update:

     * `docs/templates.md`
     * `README.md`
     * CLI help strings in `cli.py`
   * Ensure documentation reflects:

     * That `template list` and `template browse` are implemented.
     * That preview in `template browse` is **on by default**.
     * How to use `template browse` in shell pipelines.

5. **Clarity for LLM agents**

   * Prefer pure helper functions with clear signatures and small responsibilities.
   * Minimize hidden implicit behavior.
   * Avoid clever one-liners when a short, explicit block is clearer.

---

## Overview of proposed behavior

### `gai template list`

**Basic usage:**

```bash
# List all templates with default human-readable table
gai template list

# List only project templates
gai template list --tier project

# Filter by substring in logical name
gai template list --filter summarize

# Machine-readable output
gai template list --format json
```

**Default text output (example):**

```text
TIER     LOGICAL NAME                 RELATIVE PATH
project  layout/base_conversation     layout/base_conversation.j2
project  prompts/summarize            prompts/summarize.j2
user     summary                      summary.j2.md
user     email/formal                 email/formal.j2
builtin  system/default               system/default.j2
```

* Columns:

  * `TIER`: `project`, `user`, or `builtin`.
  * `LOGICAL NAME`: `TemplateRecord.logical_name_full`.
  * `RELATIVE PATH`: `TemplateRecord.relative_path.as_posix()` (within the root).

**JSON output:**

```bash
gai template list --format json
```

Example JSON array:

```json
[
  {
    "logical_name": "layout/base_conversation",
    "tier": "project",
    "relative_path": "layout/base_conversation.j2",
    "absolute_path": "/full/path/to/.gai/templates/layout/base_conversation.j2",
    "root_index": 0,
    "extension": ".j2"
  },
  {
    "logical_name": "prompts/summarize",
    "tier": "project",
    "relative_path": "prompts/summarize.j2",
    "absolute_path": "/full/path/to/.gai/templates/prompts/summarize.j2",
    "root_index": 0,
    "extension": ".j2"
  }
]
```

Notes:

* This is designed for scripting and for other tooling (including LLMs) to consume.
* Logical names are the canonical keys to use in config and `{% extends %}`.

### `gai template browse`

**Basic usage (with preview enabled by default):**

```bash
# Interactive browsing with preview pane (default)
gai template browse
```

Behavior:

* Build the template catalog (same as `list`).
* Invoke a selector (e.g. `fzf`) with:

  * One line per template.
  * A preview command that shows the contents of the selected file.
* When the user selects an entry and exits the selector:

  * Print **only** the corresponding `logical_name_full` to stdout.
  * Exit with code 0.
* On cancel (escape / ctrl-c in selector):

  * Print nothing to stdout.
  * Exit with non-zero code (for example 130 or 1).
* On error (no templates, no selector available, etc.):

  * Print a clear error message to stderr.
  * Exit with non-zero code.

**Preview behavior:**

* Preview is **on by default**.
* The strategy for flags:

  * Do **not** expose `--preview` because preview is already the default.
  * Optionally support:

    * `--no-preview` to disable preview (for minimal terminals or remote sessions).
* Example flags:

```bash
# Disable preview pane (if implemented)
gai template browse --no-preview
```

**Interaction with fzf:**

* Prefer `fzf` if available on `PATH`.
* Allow an environment variable, for example `GAI_TEMPLATE_BROWSE_COMMAND`, to override the selector command (optional but nice).
* If `fzf` is not found and no override is set:

  * Either:

    * Fail with an informative error telling user to install `fzf`, or
    * Fall back to a simple numbered menu (only if implementation remains simple and testable).
  * Strategy recommendation:

    * Start with a clear, simple behavior: require `fzf` and error out if missing, to avoid over-complicating the first implementation.
    * Document this requirement.

Example fzf invocation (conceptual):

```bash
# Pseudocode for the fzf call; actual command will be assembled in Python
fzf \
  --ansi \
  --preview 'cat {absolute_path}' \
  --preview-window=right:60%:wrap
```

Where each line fed to `fzf` contains enough information to reconstruct which `TemplateRecord` was selected.

---

## Detailed design

### New helper: building the catalog from config

**Goal:** centralize “config → roots → records → catalog” into a single helper so both commands (and possibly others) can reuse it.

**Location:** `src/gai/template_catalog.py` (preferred, since it is the natural home for catalog operations).

**Proposed helper:**

```python
from .config import get_template_roots
from .template_catalog import discover_templates, TemplateCatalog

def build_template_catalog(config: dict[str, Any]) -> TemplateCatalog:
    """Build a TemplateCatalog from the effective configuration.

    Steps:
      - Resolve template roots from config.
      - Discover templates across project/user/builtin tiers.
      - Wrap them in a TemplateCatalog.
    """
    roots = get_template_roots(config)
    records = discover_templates(
        project_roots=roots["project"],
        user_roots=roots["user"],
        builtin_roots=roots["builtin"],
    )
    return TemplateCatalog(records)
```

Notes:

* This function should not log more than necessary (debug is fine).
* It should be pure given `config`.

### CLI changes: parser and dispatch

#### Parser updates (`src/gai/cli.py`)

In `create_parser()`:

* Under the `template` subparsers, add:

1. **List subcommand:**

```python
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
```

* For `template list` we generally do not need template variables or config overrides beyond those already provided by `_add_config_and_template_args`. However, it is fine to call `_add_config_and_template_args(list_parser)` to allow users to adjust `project-template-paths`, etc., from the CLI.

2. **Browse subcommand:**

```python
    # template browse
    browse_parser = template_subparsers.add_parser(
        "browse",
        help="Interactively browse templates and select one",
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
```

* Also consider calling `_add_config_and_template_args(browse_parser)` so that template roots can be overridden when browsing.

#### Dispatch updates (`src/gai/__main__.py`)

In `_handle_new_cli`, inside the `elif parsed.command == "template":` block:

* Extend the template command handling:

```python
    elif parsed.command == "template":
        if parsed.template_command == "render":
            ...
        elif parsed.template_command == "list":
            effective_config = load_effective_config(args_list)
            from .cli import handle_template_list  # to be implemented
            handle_template_list(effective_config, parsed)
        elif parsed.template_command == "browse":
            effective_config = load_effective_config(args_list)
            from .cli import handle_template_browse  # to be implemented
            handle_template_browse(effective_config, parsed)
        else:
            parser.parse_args(["template", "-h"])
```

Notes:

* `handle_template_list` and `handle_template_browse` are helper functions you will add in `cli.py` to keep the dispatch logic thin and readable.
* These helpers will:

  * Build the catalog.
  * Apply tier and substring filters.
  * Implement the command’s behavior.
  * Handle errors and exit codes using `sys.exit` as needed.

### Implementing `handle_template_list`

**Location:** `src/gai/cli.py`, near other `handle_*` functions (e.g. after config handlers).

**Signature:**

```python
def handle_template_list(config: dict[str, Any], parsed: argparse.Namespace) -> None:
    ...
```

**Steps:**

1. Build the catalog:

   ```python
   from .template_catalog import build_template_catalog  # new helper

   catalog = build_template_catalog(config)
   ```

2. Optional filtering:

   * If `parsed.tier` is set, filter `catalog.records` by `record.tier == parsed.tier`.
   * If `parsed.filter` is set, filter by substring on `record.logical_name_full` (case-sensitive or case-insensitive; choose one and document it; case-sensitive is simpler and acceptable).

3. Handle empty catalog / no matches:

   * If no templates are discovered (after filtering):

     * For `table` format:

       * Print a friendly message such as:

         ```text
         No templates found. Check your template paths in configuration.
         ```
       * Exit with code 0 (no templates is not an error per se).
     * For `json` format:

       * Print `[]`.
       * Exit with code 0.

4. Output for `--format table`:

   * Compute rows:

     * Header: `["TIER", "LOGICAL NAME", "RELATIVE PATH"]`
     * Rows: one per `TemplateRecord`.
   * A simple manual column alignment is enough:

     * Find maximum width for each column from lines.
     * Format with spaces.
   * Print to stdout.

5. Output for `--format json`:

   * Build dictionary entries with keys:

     * `"logical_name"`
     * `"tier"`
     * `"relative_path"`
     * `"absolute_path"`
     * `"root_index"`
     * `"extension"`
   * Use `json.dumps(..., indent=2)` to print to stdout.

6. Exit normally (return `None` and let caller decide; or call `sys.exit(0)` explicitly).

### Implementing `handle_template_browse`

**Location:** `src/gai/cli.py` (same region as `handle_template_list`).

**Signature:**

```python
def handle_template_browse(config: dict[str, Any], parsed: argparse.Namespace) -> None:
    ...
```

**Design constraints:**

* Keep the logic testable by:

  * Factoring the pure “selection” logic (building a list of candidates, mapping selection back to `TemplateRecord`) into a helper function that can be tested without actually calling `fzf`.
  * Isolating the actual `subprocess.run` call into a small, easily mockable helper.

**Proposed sub-helpers:**

1. A function to filter catalog records:

   ```python
   from .template_catalog import TemplateCatalog, TemplateRecord

   def _filter_catalog_for_browse(
       catalog: TemplateCatalog,
       tier: Optional[str],
       substring: Optional[str],
   ) -> list[TemplateRecord]:
       ...
   ```

2. A function to build a list of browse entries:

   * Either just reuse `TemplateRecord` or enrich with ephemeral fields (like a human-readable label).
   * For simplicity, we can keep using `TemplateRecord` and format lines on the fly.

3. A function that runs the selector:

   ```python
   def _run_fzf_selection(
       records: list[TemplateRecord],
       preview_enabled: bool,
   ) -> Optional[TemplateRecord]:
       ...
   ```

   Implementation outlines:

   * Check `shutil.which("fzf")` or similar.
   * If not found:

     * Print an error to stderr:

       ```text
       Error: 'fzf' command not found. Please install fzf to use 'gai template browse'.
       ```
     * `sys.exit(1)`.
   * Build lines to feed into `fzf`. For example:

     * A tab-separated format:

       ```text
       {logical_name}\t{tier}\t{relative_path}\t{absolute_path}
       ```
     * Later, we can parse the selected line by splitting on `\t` and matching the logical name and tier back to a record (or just store a mapping from the full line to the record).
   * Build `fzf` arguments:

     * With preview enabled:

       * `["fzf", "--with-nth=1,2,3", "--preview", "cat {4th_field}", "--delimiter", "\t"]`
       * Note: constructing the preview command may require Python to fill in placeholders. You can also use `--preview 'cat {4}'` with `--with-nth` and `--delimiter` if it remains readable.
     * Without preview:

       * Omit the `--preview` flags.
   * Run `subprocess.run(..., input=encoded_lines, capture_output=True, text=True)`.
   * Check `returncode`:

     * `0`: selection made; parse stdout’s single line.
     * Non-zero: treat as cancel (no selection) and exit with a non-zero code.
   * Map the selected line back to a `TemplateRecord`. A simple way:

     * Keep a dictionary `line -> record` when building lines.

**Main `handle_template_browse` steps:**

1. Build catalog via `build_template_catalog(config)`.

2. Filter by tier and substring via `_filter_catalog_for_browse`.

3. If no records remain:

   * Print message to stderr:

     ```text
     No templates available to browse after applying filters.
     ```
   * Exit with non-zero code (e.g. 1).

4. Call `_run_fzf_selection(records, preview_enabled = not parsed.no_preview)`.

5. If `_run_fzf_selection` returns a `TemplateRecord`:

   * Print only `record.logical_name_full` to stdout.
   * Exit with code 0.

6. If `_run_fzf_selection` returns `None` (if you choose to encode cancel like this):

   * Exit with non-zero code.

### Error handling and edge cases

* **No template roots configured or reachable:**

  * `build_template_catalog` will return an empty `TemplateCatalog`.
  * `template list`:

    * Table: print “No templates found.” and exit 0.
    * JSON: print `[]` and exit 0.
  * `template browse`:

    * Print a clear message to stderr and exit with non-zero.

* **Invalid tier filter argument:**

  * Argparse will handle invalid `--tier` via `choices`, so you do not need custom validation.

* **Filters that match nothing:**

  * Same as empty catalog after filtering.

* **Selector errors / missing fzf:**

  * Treat as fatal for `template browse`.
  * Provide clear, actionable error message.

---

## Testing strategy (always separate tests from code)

### General constraints

* **All tests must live under `tests/`**.
  Do not add any test logic or test-only entry points under `src/gai`.

* Keep tests focused and explicit. Aim for function-level tests for:

  * Catalog building and filtering.
  * Formatting and JSON serialization.
  * Selector orchestration (using mocks in place of actual `fzf`).

### Suggested test modules and coverage

1. **`tests/test_template_catalog_building.py`**

   * Test `build_template_catalog(config)`:

     * Use temporary directories with fake template files (`.j2`, `.j2.md`).
     * Control `project-template-paths` and `user-template-paths` via a fake config dict.
     * Assert that:

       * All created templates are discovered.
       * Tiers and logical_names are correct.

2. **`tests/test_template_list_cli.py`**

   * Tests for `handle_template_list`:

     * Use a small catalog built from temporary dirs.
     * Mock `sys.stdout` using `io.StringIO`.
     * Verify:

       * Table output formatting contains the expected lines.
       * JSON format is valid and contains the correct fields.
       * Empty catalog yields “No templates found.” or `[]` as described.

3. **`tests/test_template_browse_logic.py`**

   * Do not run actual `fzf`. Instead:

     * Factor out the record-to-line mapping and selection mapping into pure functions that you can test.
     * Optionally, if `_run_fzf_selection` is small and isolated, you can patch `subprocess.run` to simulate `fzf` behavior.
   * Test:

     * That filtering by tier and substring behaves as expected.
     * That “cancel” (simulated via non-zero returncode) leads to non-zero exit code.
     * That a selected line is correctly mapped back to `TemplateRecord.logical_name_full`.

4. **Integration tests (optional but nice)**

   * If your test harness permits, you can run `python -m gai template list` with environment variables to point to temporary template directories and assert on output.
   * This is optional and may be more fragile, but it improves confidence.

---

## Documentation and help updates

### `docs/templates.md`

Update the “Future CLI commands” section to describe the **implemented** commands. Key changes:

1. Replace “Future CLI commands” with something like “CLI commands for working with templates”.

2. Replace “planned usage” examples with actual syntax:

   * For `template list`:

     ```bash
     # List all templates
     gai template list

     # List only project templates
     gai template list --tier project

     # Filter by name and emit json
     gai template list --filter summarize --format json
     ```

   * For `template browse`:

     ```bash
     # Interactively browse templates with a default preview pane
     gai template browse

     # Browse only project templates
     gai template browse --tier project

     # Browse without preview
     gai template browse --no-preview
     ```

3. Explicitly describe:

   * That `template list` and `template browse` are built on the same catalog and precedence rules described earlier in the document.
   * That `gai template browse` prints only the **logical template name** on stdout, so it can be used in shell substitution:

     ```bash
     gai config set user-instruction-template "$(gai template browse)"
     ```
   * That preview is enabled by default; `--no-preview` disables it.

4. Remove or correct any references to `gai template browse --preview` and ensure they do not suggest that preview is opt-in.

### `README.md`

1. In the “Template system” or related sections, add a short subsection about template discovery:

   ````markdown
   ### Template discovery and browsing

   You can inspect available templates using the template catalog commands:

   ```bash
   # List all templates discovered from project, user, and builtin tiers
   gai template list

   # Interactively browse templates with a preview pane
   gai template browse
   ````

   The browse command prints only the logical template name of the selection to stdout, making it easy to wire into configuration:

   ```bash
   gai config set user-instruction-template "$(gai template browse)"
   ```

   ```
   ```
2. Ensure the wording is consistent with sentence case and with `docs/templates.md`.

### CLI help strings (`create_parser` in `cli.py`)

* Update the main epilog (if needed) to mention `template list` and `template browse` briefly.
* Make sure `template` subparser help text is clear:

  * `template list` → “List discovered templates in catalog order”
  * `template browse` → “Interactively browse templates and select one (preview enabled by default)”

---

## Implementation order of work

For an LLM agent or human contributor, the recommended order is:

1. **Plumbing and helpers**

   * Add `build_template_catalog` in `template_catalog.py`.
   * Ensure it is used in `render_system_instruction` and `render_user_instruction` as well (if desired) for consistency, or leave those as-is if they already do equivalent work.

2. **CLI changes**

   * Update `create_parser` to add `template list` and `template browse`.
   * Add `handle_template_list` and `handle_template_browse` in `cli.py`.
   * Wire them in `_handle_new_cli` in `__main__.py`.

3. **Core functionality**

   * Implement the logic in `handle_template_list`, including table and JSON output.
   * Implement the logic in `handle_template_browse`, including fzf-based selection and default preview.

4. **Tests**

   * Add tests under `tests/` (no test code in `src/gai`).
   * Cover catalog building, listing behavior, and browse selection logic.

5. **Documentation**

   * Update `docs/templates.md` to describe the now-implemented commands and correct the preview semantics.
   * Update `README.md` with examples of `template list` and `template browse`.

6. **Polish**

   * Check help output:

     * `gai --help`
     * `gai template --help`
     * `gai template list --help`
     * `gai template browse --help`
   * Ensure sentence case in headings and descriptions.
   * Confirm logging behaves consistently and does not pollute stdout for machine-readable output.

---

## Explicit instructions for LLM implementers

When you, as an LLM, are asked to implement this strategy in the `gai` repository:

1. **Always keep tests separate from production code.**

   * Add or modify production logic only in `src/gai/...`.
   * Add or modify tests only in `tests/...`.

2. **Reuse existing abstractions.**

   * Do not reimplement catalog discovery; use `get_template_roots` and `discover_templates`, wrapped by `build_template_catalog`.
   * Use `TemplateRecord` and `TemplateCatalog` instead of creating parallel representations.

3. **Be explicit and conservative about external dependencies.**

   * When adding `fzf` integration, guard the call with `shutil.which("fzf")` or equivalent.
   * Provide clear error messages if the external tool is missing.

4. **Maintain consistent semantics.**

   * Make sure `gai template list` and `gai template browse` show and operate on the same set of templates that `render_system_instruction` / `render_user_instruction` would see.
   * Keep preview enabled by default in `template browse`. If you add `--no-preview`, ensure it inverts the default behavior.

5. **Update documentation and help.**

   * After editing code, update:

     * `docs/templates.md`
     * `README.md`
     * Any relevant help text in `cli.py`
   * Ensure that any example using `gai template browse` does not mention `--preview` but explains that preview is default.

6. **Do not silently change unrelated behavior.**

   * Avoid refactors that alter behavior of existing commands (`generate`, `config`, `template render`) unless absolutely necessary.
   * If you must touch shared code, keep changes minimal, and reason through backward compatibility.

By following this strategy, the implementation of `gai template list` and `gai template browse` will align with the existing design philosophy of `gai`, provide a consistent mental model for users, and be straightforward for both humans and LLMs to maintain and extend.
