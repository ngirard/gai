## Overview

This document is an implementation strategy for adding robust, name-based, Obsidian-style templating to the `gai` project, on top of the specification you saved as `goals/templates/Specification.md`.

It is written for LLM agents (and humans) who will implement the feature. It:

* recaps the relevant context and design decisions from our brainstorming;
* describes the current state of the codebase that matters for templates;
* breaks the work into phases and concrete tasks;
* specifies where to put new code, new tests, and new documentation.

One strict requirement: **always keep tests separate from production code** (for example under `tests/` or equivalent).

Another: **always update documentation and help strings** when behaviors change or new user-facing features are added.

---

## Context recap from our brainstorming

This section restates the conceptual context so that this file plus the specification are sufficient for an LLM to work without reading the conversation.

### Current philosophy

The `gai` tool is intentionally strict:

* it uses `jinja2.StrictUndefined`, so missing template variables raise errors instead of being silently treated as empty strings;
* configuration values are strongly typed and conversion errors (`ConfigError`) are raised early;
* the goal is **correctness over convenience**: we prefer the program to halt loudly rather than quietly doing the wrong thing.

We want this same philosophy to apply to template discovery and resolution:

* ambiguous template names must be treated as errors, not resolved arbitrarily;
* missing templates must produce clear, actionable errors;
* the rules for how names are resolved must be simple enough that users can form a reliable mental model.

### Desired template experience

We want to allow composition of templates (via `{% extends %}`, `{% include %}`, `{% import %}`) in a way that is:

* robust and deterministic;
* configurable via template roots and tiers (project > user > builtin);
* ergonomically similar to Obsidian-style wikilinks, i.e. extensionless logical names like `"layout/base_conversation"` or `"summary"`.

Key design points:

* **logical names** are extensionless and are what appears inside Jinja tags (`extends`, `include`, `import`) and in config keys like `user-instruction-template`;
* **physical template files** are normal files with extensions `.j2` or `.j2.md`; editors can use syntax highlighting etc.;
* **template roots** are directories configured at project, user, and builtin tiers;
* **tiers** have precedence: `project` > `user` > `builtin` (closest to the project wins);
* **catalog** is a data structure that represents all known templates across all tiers and roots, and is the single source of truth for:

  * resolution (mapping logical names to template files),
  * listing and browsing (e.g. for a future `fzf`-based selector).

Homonymy (multiple candidate templates for the same logical name) is handled strictly:

* resolution looks tier by tier (project, then user, then builtin);
* the first tier where matches are found is the **only** tier considered;
* if that tier yields exactly one candidate, it is used;
* if that tier yields more than one candidate, this is an **ambiguity error** and the program halts with a helpful message;
* only if a tier yields zero candidates do we continue to lower tiers.

Extension ambiguity is also strict:

* if the user uses an **extensionless** name (e.g. `"summary"`) and, at the first matching tier, there are two physical files `summary.j2` and `summary.j2.md`, this is considered ambiguous, not auto-resolved;
* the user can disambiguate by:

  * using an explicit extension (`"summary.j2"`),
  * using a more specific path-based logical name (`"email/summary"`), or
  * removing or renaming duplicate files.

This mirrors the `StrictUndefined` philosophy: “**exactly one sensible interpretation or fail**”.

---

## Current codebase relevant to templates

The repository snapshot shows the following key files:

* `src/gai/config.py`

  * defines `DEFAULT_CONFIG` and `CONFIG_TYPES`;
  * handles loading config from user and repo files and from CLI (`--conf-*`);
  * contains `read_file_content` and `_resolve_config_file_paths`, which implement `@:path` semantics for config values (`system-instruction` and `user-instruction`).

* `src/gai/templates.py`

  * defines `create_jinja_env()`:

    * uses `jinja2.Environment` with `FileSystemLoader(searchpath=".")`;
    * uses `jinja2.StrictUndefined`, no autoescape, trimmed blocks;
  * defines a global `JINJA_ENV`;
  * defines `render_template_string(template_str, template_variables, template_name)`:

    * uses `JINJA_ENV.from_string(str(template_str))`;
    * does not use named templates or the loader for file-based resolution.

* `src/gai/generation.py`

  * `prepare_prompt_contents(config, template_variables)`:

    * obtains `user-instruction` from config (string or file contents via `@:`);
    * calls `render_template_string` with `template_name="user-instruction"`.
  * `prepare_generate_content_config_dict(config, template_variables)`:

    * obtains `system-instruction` from config;
    * calls `render_template_string` with `template_name="system-instruction"`.
  * `generate(...)`:

    * uses the above to prepare text passed into the Gemini API.

* `src/gai/cli.py`

  * `show_rendered_prompt(config, template_variables, part)`:

    * calls `render_template_string` for system and user instructions;
    * prints the result.
  * CLI currently does not have subcommands for listing or browsing templates.

* `src/gai/exceptions.py`

  * defines `GaiError` and specific subclasses (`ConfigError`, `TemplateError`, etc.).
  * There is no explicit `TemplateNotFound` or `TemplateAmbiguityError` yet.

Currently, templates are only rendered as **literal strings** or from file contents referenced via `@:path`, never via named templates resolved through a loader’s `get_template`. Composition across files is possible only if the user manually sets up a loader and uses name-based templates, which we do not do yet.

---

## High-level implementation plan

The implementation can be broken into the following phases:

1. **Introduce a template catalog and name resolution layer** (pure Python, no behavior change for existing configs yet).
2. **Extend `templates.py` with a smarter environment and loader** that use the catalog and support extensionless logical names.
3. **Extend configuration to support template roots and named templates** (`*-template` fields) while preserving backward compatibility.
4. **Wire named template resolution into generation and CLI** (and define clear precedence between named templates and literal / `@:path` templates).
5. **Add tests** for catalog building, resolution, ambiguity behavior, and backward compatibility.
6. **Update documentation** (README and dedicated docs) and prepare for future CLI commands for browsing templates.

Each phase should be test-driven: write tests first (or in parallel) under a dedicated `tests/` structure.

---

## Phase 1: introduce a template catalog

### Objectives

* Create a reusable component that:

  * discovers template files in configured roots;
  * constructs a catalog of template records with all necessary metadata;
  * orders them according to tier and root order;
* Does **not** yet change how existing templates are rendered.

### Tasks

1. **Define data structures**

   In `src/gai/templates.py` (or a small new module if you prefer), define:

   * an enum-like structure or `Literal` types for tiers: `"project"`, `"user"`, `"builtin"`.
   * a `TemplateRecord` data structure, potentially using `dataclasses.dataclass`, with fields as defined in the specification:

     * `logical_name_full: str`
     * `relative_path: pathlib.Path` (or `str`)
     * `absolute_path: pathlib.Path`
     * `tier: str` (or enum)
     * `root_index: int`
     * `extension: str`

   Make this independent of Jinja so that it can be used for listing even without an environment.

2. **Define configuration-level tiered root resolution**

   Decide where to resolve the following new config keys (later added in phase 3, but plan now):

   * `project-template-paths: list[str] | None`
   * `user-template-paths: list[str] | None`
   * `builtin-template-paths: list[str] | None`

   Strategy:

   * In `config.py`, after loading and merging config, expand them into absolute paths; resolution rules may include:

     * expanding `~` to the user’s home directory;
     * resolving relative paths against:

       * project root (for project tier);
       * home directory or config directory (for user tier);
       * install-time known directory (for builtin tier), if used.
   * For phase 1, you may simulate these or use defaults (e.g. `[".gai/templates"]` for project and `["~/.config/gai/templates"]` for user) but actual defaults can be deferred to phase 3.

3. **Implement discovery**

   Implement a function, for example:

   ```python
   def discover_templates(
       project_roots: list[pathlib.Path],
       user_roots: list[pathlib.Path],
       builtin_roots: list[pathlib.Path],
       allowed_extensions: tuple[str, ...] = (".j2", ".j2.md"),
   ) -> list[TemplateRecord]:
       ...
   ```

   Use the algorithm from the specification:

   * iterate tiers in order: project, then user, then builtin;
   * iterate roots in the config-provided order;
   * skip missing roots but log at `INFO` or `DEBUG`;
   * recursively walk each root (`rglob("*")`);
   * for each regular file with a recognized extension:

     * compute `relative_path` (root-relative);
     * define `logical_name_full` as `relative_path` without extension, with `/` as separator;
     * compute `extension` as the file suffix including the dot;
     * create a `TemplateRecord` and add it to the list.

   Ensure the function returns the list in the order specified in the spec (tier precedence, then root order, then relative path sort).

4. **Expose a catalog builder**

   Optionally, wrap `discover_templates` in a small `TemplateCatalog` class that can:

   * hold `records: list[TemplateRecord]`;
   * provide utility methods for:

     * filtering by tier;
     * grouping by name;
     * performing resolution (next phase).

   For phase 1, the minimal piece is the pure discovery function and its return value.

5. **Write tests for discovery**

   Create tests under `tests/` (for example `tests/test_templates_discovery.py`).

   Each test should:

   * set up temporary directories for project/user/builtin roots using `tmp_path` or similar;
   * create sample template files (use simple contents, the content does not matter yet);
   * call `discover_templates`;
   * assert:

     * the number of records;
     * `logical_name_full` values;
     * ordering by tier and root index;
     * correct handling of multiple roots in a tier;
     * ignoring of non-existing paths.

   Keep tests purely about discovery; do not involve Jinja or rendering yet.

---

## Phase 2: implement logical name resolution and smart loader

### Objectives

* Implement the resolution algorithm described in the spec:

  * path-specific vs basename-only names;
  * tier-aware resolution;
  * strict handling of ambiguity;
  * explicit extension handling.
* Plug this resolver into a custom Jinja loader that supports extensionless logical names in `{% extends %}` and `{% include %}`.

### Tasks

1. **Define template resolution functions**

   In `templates.py`, define a resolution API such as:

   ```python
   class TemplateResolutionError(TemplateError):
       ...

   class TemplateNotFoundError(TemplateResolutionError):
       ...

   class TemplateAmbiguityError(TemplateResolutionError):
       ...

   def resolve_template_name(
       catalog: list[TemplateRecord],
       logical_name: str,
       allowed_extensions: tuple[str, ...] = (".j2", ".j2.md"),
   ) -> TemplateRecord:
       ...
   ```

   Implement:

   * detection of explicit extension (`name` ending with `.j2` or `.j2.md`);
   * splitting into path-specific vs basename-only:

     * `"/" in base_name` → path-specific;
     * else basename-only;
   * tier-aware matching:

     * group records by tier (in the precedence order);
     * for each tier:

       * compute `tier_candidates` according to the spec;
       * if `len == 0`, continue;
       * if `len == 1`, return that record;
       * if `len > 1`, raise `TemplateAmbiguityError` with details;
   * if no tier yields candidates, raise `TemplateNotFoundError`.

   Extension-specific details:

   * if the user includes an extension in the logical name, restrict matches to that extension;
   * if not, then extension differences among candidates are treated as ambiguity.

2. **Implement a smart Jinja loader**

   Define a loader subclass, for example:

   ```python
   class CatalogLoader(jinja2.BaseLoader):
       def __init__(self, catalog: list[TemplateRecord]):
           self._catalog = catalog
           ...

       def get_source(self, environment, template: str):
           # template is the logical name as used in Jinja
           record = resolve_template_name(self._catalog, template)
           # read file contents, return Jinja get_source triple
   ```

   Requirements:

   * `get_source` must:

     * call `resolve_template_name` with the catalog and the logical name as passed by Jinja;
     * read the contents from `record.absolute_path` as text (`utf-8`);
     * compute `mtime` for Jinja’s reloader if needed;
     * define `uptodate` appropriately (you can ignore hot-reload in a first version and return a trivial function that always returns `False`, or better: check file mod time).
   * errors from `resolve_template_name` should be translated into `jinja2.TemplateNotFound` for Jinja, but **must** preserve information for higher layers, potentially by wrapping or storing the original exception as the cause.

3. **Integrate catalog and loader into environment creation**

   Replace the previous `create_jinja_env` and global environment pattern with one that:

   * is instantiated with a `TemplateCatalog` (or list of `TemplateRecord`) and config-derived roots;
   * uses `CatalogLoader` as the loader instead of `FileSystemLoader(".");
   * still uses `StrictUndefined`, `trim_blocks=True`, `lstrip_blocks=True`.

   Proposed interface:

   ```python
   def create_jinja_env_from_catalog(
       catalog: list[TemplateRecord],
   ) -> jinja2.Environment:
       env = jinja2.Environment(
           loader=CatalogLoader(catalog),
           undefined=jinja2.StrictUndefined,
           autoescape=False,
           trim_blocks=True,
           lstrip_blocks=True,
       )
       return env
   ```

   Keep the old `create_jinja_env()` for compatibility for literal templates (phase 4 will refine this).

4. **Write tests for resolution and loader**

   Add tests like `tests/test_templates_resolution.py`:

   * build small catalogs manually (no filesystem needed) and assert:

     * resolving `"summary"` finds the correct tier’s unique candidate;
     * ambiguous tier raises `TemplateAmbiguityError` with expected message and candidates;
     * missing name raises `TemplateNotFoundError`;
     * explicit extension selects the right candidate, even when there are multiple.
   * test `CatalogLoader` by constructing a `jinja2.Environment` with it and:

     * creating temporary files matching the catalog records;
     * using `env.get_template("logical/name")` and rendering to assert content;
     * verifying that ambiguity leads to an exception (likely `TemplateNotFound` wrapping your `TemplateAmbiguityError`).

   Keep these tests isolated from the existing `render_template_string` until phase 4.

---

## Phase 3: extend configuration for template roots and named templates

### Objectives

* Add configuration keys for template roots and named template selection.
* Maintain backward compatibility for existing configs using `system-instruction` and `user-instruction` (literal or via `@:path`).
* Make sure config and template layers have a clean separation of responsibility.

### Tasks

1. **Add new config keys**

   In `config.py`:

   * extend `DEFAULT_CONFIG` to include (with suitable defaults, possibly `None`):

     ```python
     DEFAULT_CONFIG = {
         ...
         "project-template-paths": None,  # or [] to mean no project roots by default
         "user-template-paths": None,
         "builtin-template-paths": None,
         "system-instruction-template": None,
         "user-instruction-template": None,
     }
     ```

   * extend `CONFIG_TYPES` accordingly:

     * `project-template-paths`, `user-template-paths`, `builtin-template-paths` → list;
     * `system-instruction-template`, `user-instruction-template` → str.

2. **Determine default paths**

   Decide on defaults for template roots, possibly:

   * `project-template-paths` default to `[".gai/templates"]` (interpreted relative to repo root if inside a Git repo, or `cwd` otherwise);
   * `user-template-paths` default to `["~/.config/gai/templates"]`;
   * `builtin-template-paths` may be `None` initially or a single packaged directory.

   Document these defaults and ensure they are resolved into absolute paths somewhere (either in config or in templates module).

3. **Resolve template roots into absolute paths**

   Implement a function, possibly in `config.py` or `templates.py`, that accepts the final merged config dict and returns:

   ```python
   def get_template_roots(config: dict[str, Any]) -> dict[str, list[pathlib.Path]]:
       # returns e.g. {"project": [...], "user": [...], "builtin": [...]}
   ```

   Resolution rules:

   * expand `~` using `Path.expanduser()`;
   * for project roots, resolve relative paths against the repo root if there is one (`find_git_repo_root`) or `cwd` otherwise;
   * for user roots, resolve relative paths against the user config directory or home directory;
   * for builtin roots, if any, resolve against package data directories.

4. **Validate config**

   Extend `_convert_config_values` and `_resolve_config_file_paths` carefully:

   * `@:` resolution should remain only for `system-instruction` and `user-instruction`, not for `*-template` keys (those are always logical names, not file paths);
   * unknown keys remain warnings as before.

5. **Write config tests**

   Add tests for:

   * the presence and types of the new keys in `DEFAULT_CONFIG`;
   * correct resolution of template root paths in `get_template_roots`, including:

     * expansion of `~`;
     * behavior with and without a Git repo;
     * ignoring non-existing directories while logging.

   Use small, focused tests in `tests/test_config_templates.py` (or similar) to keep template-related config logic grouped.

---

## Phase 4: integrate named templates into rendering

### Objectives

* Allow configuration to refer to templates by **logical name** (`*-instruction-template`) instead of literal inline strings or `@:file`.
* Preserve backwards compatibility with existing literal / `@:path` behavior.
* Ensure a clear precedence rule between named templates and literal templates.

### Precedence rule

Define a specific, simple rule that must be enforced and documented:

* For each of system and user instructions:

  1. If `*-instruction-template` (name) is set, use it and ignore `*-instruction` (literal), even if it is also set.
  2. Otherwise, fall back to the existing logic:

     * `*-instruction` from config (a string);
     * with possible `@:` file indirection already resolved in config.

This ensures explicit template naming takes precedence over legacy literal configuration, and the behavior is easy to describe.

### Tasks

1. **Update `templates.py` to support both modes**

   You will have two primary rendering paths:

   * **named template rendering**, using the catalog and loader:

     * build the catalog using `get_template_roots(config)` and `discover_templates`;
     * build a `jinja2.Environment` using `create_jinja_env_from_catalog(catalog)`;
     * call `env.get_template(logical_name)` and render with `template_variables`.

   * **inline/literal rendering**, using something like the existing `render_template_string`:

     * use `env.from_string(...)`, possibly with a lightweight environment that has no loader or an inert loader.

   You should provide helper functions to avoid duplication, for example:

   ```python
   def render_system_instruction(config: dict[str, Any], template_vars: dict[str, Any]) -> Optional[str]:
       ...

   def render_user_instruction(config: dict[str, Any], template_vars: dict[str, Any]) -> str:
       ...
   ```

   Internally, these:

   * check for `*-instruction-template`;
   * if present:

     * build or reuse a catalog;
     * create an environment with `CatalogLoader`;
     * load and render the named template;
   * if absent:

     * fallback to existing `render_template_string` path.

   Decide whether to reuse a single environment per call, cache at module level, or pass an environment through; start simple (per-call) and optimise later if necessary.

2. **Update `generation.py`**

   Replace direct calls to `render_template_string` with calls to the new high-level helpers:

   * in `prepare_prompt_contents`, use `render_user_instruction(...)`;
   * in `prepare_generate_content_config_dict`, use `render_system_instruction(...)`.

   These functions must accept the same `config` and `template_variables` and return strings or `None` as before, so `generation.py` can remain mostly unchanged apart from function names.

3. **Update `cli.show_rendered_prompt`**

   In `cli.py`, `show_rendered_prompt` should also use the same helpers to ensure CLI output and `generate` behavior are consistent:

   * for system part: call `render_system_instruction(...)`;
   * for user part: call `render_user_instruction(...)`;
   * keep the printing logic the same (combine into `<system_instruction>...</system_instruction>` etc.).

4. **Error handling**

   Ensure that:

   * `TemplateNotFoundError` and `TemplateAmbiguityError` are caught and converted into `TemplateError` or shown as user-friendly messages with:

     * logical name;
     * tier;
     * candidate paths;
   * CLI exit codes remain consistent with existing exception handling in `__main__.py`.

5. **Write integration tests**

   Add tests that:

   * set up config with:

     * `project-template-paths` pointing to a temp directory;
     * `user-instruction-template = "user/default"` etc.;
   * create template files under project and/or user roots with simple Jinja content;
   * ensure:

     * `prepare_prompt_contents` uses the named templates and resolves includes/extends correctly;
     * `show_rendered_prompt` outputs the expected result;
   * tests for precedence:

     * when both `user-instruction-template` and `user-instruction` are set, the named template is used;
     * when `user-instruction-template` is not set, literal behavior is unchanged.

   Place these in `tests/test_generation_templates_integration.py` or similar.

---

## Phase 5: tests, edge cases, and robustness

### Objectives

* Ensure all key behaviors are covered by unit tests.
* Explicitly test edge cases around ambiguity and errors.

### Edge cases to test

* **Ambiguous basename-only names**:

  * two `summary.*` files in the same tier:

    * `summary.j2`;
    * `email/summary.j2`.
  * ensure `{% extends "summary" %}` raises ambiguity;
  * ensure `{% extends "email/summary" %}` resolves correctly.

* **Ambiguous extensions for the same logical path**:

  * `summary.j2` and `summary.j2.md` in same tier;
  * `{% extends "summary" %}` → ambiguity;
  * `{% extends "summary.j2" %}` → resolves.

* **Tier precedence**:

  * same logical name in project and user tiers:

    * project one wins;
    * user templates are ignored for that name;
  * same ambiguity only in user tier:

    * if project has no candidates, user ambiguity is fatal.

* **Missing template roots**:

  * nonexistent project template directory configured;
  * ensure discovery logs a message but does not crash;
  * resolution fails with “template not found” if no other roots provide the template.

* **Interaction with `@:path`**:

  * config uses only `user-instruction` via `@:somefile`;
  * no `user-instruction-template` set;
  * ensure behavior is unchanged vs previous versions;
  * assert no catalog is required in this path.

Each of these should be covered in tests under `tests/`, grouped logically.

---

## Phase 6: documentation and future CLI subcommands

### Objectives

* Document the new template system clearly for users.
* Lay groundwork for a future `template` subcommand that lists, browses, and selects templates (possibly with `fzf`).

### Documentation tasks

1. **Update README**

   Add a section “Template system” or similar that explains:

   * what template roots are;
   * the three tiers (project, user, builtin) and their precedence;
   * how to configure:

     * `project-template-paths`;
     * `user-template-paths`;
     * `*-instruction-template` keys;
   * how logical names are resolved:

     * extensionless names;
     * path-specific vs basename-only names;
     * ambiguity rules (fail on multiple candidates);
     * tier precedence.
   * examples:

     * directory layout;
     * sample templates using `{% extends "layout/base_conversation" %}` etc.;
     * small config snippet showing `user-instruction-template = "user/default"`.

2. **Add a separate markdown doc**

   In a path like `docs/templates.md` or `goals/templates/Overview.md`, include:

   * a condensed version of the specification and strategy;
   * examples of how to structure template directories;
   * guidance for avoiding ambiguity:

     * keep names unique when using basenames;
     * use path segments (`partials/header` vs `header`) to disambiguate;
     * do not keep multiple extensions for the same base name unless you always reference them with explicit extensions.

3. **Describe future CLI ideas**

   In docs (and optionally as `TODO` comments), outline the intended `gai template` subcommands, for example:

   * `gai template list`:

     * uses the catalog to list all templates with tier, logical name, and relative path;
     * respects the catalog ordering.
   * `gai template browse`:

     * pipes the catalog into `fzf` for interactive selection;
     * shows template contents in a preview pane using `absolute_path`;
     * returns the selected logical name for use in config.

   Emphasize that these commands must reuse the same catalog and resolution logic, not reimplement discovery.

---

## General guidance for LLM implementers

* Keep code and tests separate:

  * production code stays under `src/gai/`;
  * tests go under `tests/`, with filenames that mirror the module under test.
* Respect the strictness philosophy:

  * never silently pick an arbitrary candidate when ambiguity exists;
  * do not introduce “fallback” behavior that contradicts the resolution specification.
* Avoid surprising magic:

  * when in doubt, prefer explicit errors with actionable messages over implicit behavior;
  * always include logical names and candidate paths in ambiguity errors.
* Keep the specification (`Specification.md`) and this strategy (`Strategy.md`) as the source of truth:

  * if implementation decisions deviate from these, update both the code and these documents;
  * update user-facing docs any time a user-visible behavior changes.

If you follow this strategy step by step, you will end up with:

* a rigorous template discovery and resolution system;
* a consistent “one catalog, many uses” model (resolution, listing, browsing);
* Obsidian-like, extensionless template names that remain safe and predictable.
