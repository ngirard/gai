# Template System Documentation

This document provides comprehensive documentation for the `gai` template system, which enables powerful, composable, and organized prompt templates using Jinja2 with Obsidian-style logical names.

## Table of Contents

- [Overview](#overview)
- [Core Concepts](#core-concepts)
- [Configuration](#configuration)
- [Template Discovery and Resolution](#template-discovery-and-resolution)
- [Using Named Templates](#using-named-templates)
- [Template Composition](#template-composition)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [CLI Commands for Working with Templates](#cli-commands-for-working-with-templates)

## Overview

The `gai` template system provides:

1. **Organized template structure**: Templates are organized in configurable directories (template roots) with a clear tier precedence system
2. **Logical names**: Use extensionless, Obsidian-style names like `"summary"` or `"layout/base_conversation"` instead of file paths
3. **Template composition**: Use Jinja2's `{% extends %}`, `{% include %}`, and `{% import %}` to build complex templates from reusable components
4. **Strict correctness**: Ambiguous template names cause errors rather than silently auto-resolving
5. **Discoverable templates**: All templates are cataloged and can be listed/browsed (via future CLI commands)

### Philosophy

The template system follows `gai`'s core philosophy of **correctness over convenience**:

- Missing templates produce clear, actionable errors
- Ambiguous template names (multiple candidates) fail loudly rather than picking arbitrarily
- Template variables use `StrictUndefined`, so typos are caught immediately
- The resolution rules are simple and predictable

## Core Concepts

### Template Root

A **template root** is a directory that is searched for template files. Examples:

- Project root templates: `<project>/.gai/templates`
- User root templates: `~/.config/gai/templates`
- Builtin root templates: A directory packaged inside `gai`

### Tier

A **tier** is a named group of template roots with a defined precedence. The three tiers are:

1. **`project`**: Templates closest to the current repository or working directory (highest precedence)
2. **`user`**: User-level templates, typically under the home directory (medium precedence)
3. **`builtin`**: Read-only templates that ship with the tool (lowest precedence)

Higher tiers override lower tiers when resolving a logical name. Within a tier, all roots are considered at the same "distance".

### Template File

A **template file** is a physical file under a template root whose extension is one of the recognized template extensions:

- Recognized extensions: `.j2`, `.j2.md`
- One file = one template
- Files can be nested in subdirectories for organization

### Logical Template Name

A **logical template name** is the string that appears inside Jinja `{% extends %}`, `{% include %}`, and `{% import %}` statements, and in configuration keys like `user-instruction-template`.

Key properties:

- **Extensionless by default**: Use `layout/base_conversation` instead of `layout/base_conversation.j2`
- **Forward slashes**: Use `/` as path separator, even on Windows
- **Relative to template roots**: Names are interpreted relative to configured template roots
- **Optional explicit extension**: Can include `.j2` or `.j2.md` for advanced disambiguation

Examples:

- `summary` - basename-only name
- `layout/base_conversation` - path-specific name
- `email/summary.j2` - explicit extension (advanced usage)

### Template Catalog

The **template catalog** is a data structure produced by discovery that represents all known template files, enriched with metadata and ordered according to precedence rules. The catalog is the single source of truth for:

- Template name resolution (mapping logical names to files)
- Future listing and browsing commands

## Configuration

### Configuration Keys

Configure template roots and named templates in your configuration file (TOML format):

```toml
# Template root directories (list of paths)
project-template-paths = [".gai/templates"]
user-template-paths = ["~/.config/gai/templates"]
builtin-template-paths = []  # Optional, typically empty

# Named template references (logical names)
system-instruction-template = "system/expert_analyst"
user-instruction-template = "prompts/summarize"
```

### Path Resolution

Paths in `*-template-paths` configuration keys are resolved as follows:

- **Tilde expansion**: `~` expands to the user's home directory
- **Relative paths**:
  - `project-template-paths`: Resolved relative to the repository root (if in a Git repo) or current working directory
  - `user-template-paths`: Resolved relative to the user's config directory or home directory
  - `builtin-template-paths`: Resolved relative to package installation directory
- **Absolute paths**: Used as-is
- **Non-existent paths**: Ignored with a debug log message (not an error)

### Default Paths

If not explicitly configured, the following defaults are used:

- `project-template-paths`: `[".gai/templates"]`
- `user-template-paths`: `["~/.config/gai/templates"]`
- `builtin-template-paths`: `[]` (empty by default)

### Template Precedence

When multiple configuration sources specify template-related settings, the following precedence applies (later overrides earlier):

1. Script defaults
2. User configuration file (`~/.config/gai/config.toml`)
3. Repository configuration file (`.gai/config.toml`)
4. Command-line arguments (`--conf-*`)

For template resolution within the catalog, tier precedence applies:

1. `project` tier (highest precedence)
2. `user` tier
3. `builtin` tier (lowest precedence)

## Template Discovery and Resolution

### Discovery Process

Template discovery scans configured template roots to build a catalog:

1. **Process tiers in order**: project → user → builtin
2. **Process roots within each tier**: In the order listed in configuration
3. **Recursively scan each root**: Find all files with recognized extensions (`.j2`, `.j2.md`)
4. **Create template records**: Each file becomes a catalog entry with:
   - `logical_name_full`: Path without extension (e.g., `layout/base_conversation`)
   - `relative_path`: Path within its root (e.g., `layout/base_conversation.j2`)
   - `absolute_path`: Full filesystem path
   - `tier`: One of `project`, `user`, `builtin`
   - `root_index`: Position of root within its tier
   - `extension`: File extension (e.g., `.j2`)

### Resolution Algorithm

When resolving a logical name like `"summary"`:

1. **Check for explicit extension**:
   - If name ends with `.j2` or `.j2.md`, extract it as `required_extension`
   - Otherwise, `required_extension` is `None`

2. **Determine name type**:
   - **Path-specific** (contains `/`): Must match `logical_name_full` exactly
   - **Basename-only** (no `/`): Matches last path segment of `logical_name_full`

3. **Search tiers in order** (project → user → builtin):
   - Find all candidates in the current tier matching the name
   - If extension was explicit, also match the extension
   - If **zero candidates**: Continue to next tier
   - If **one candidate**: Success! Return this template
   - If **multiple candidates**: Raise `TemplateAmbiguityError` (do not look at lower tiers)

4. **No candidates in any tier**: Raise `TemplateNotFoundError`

### Example Resolution

Given this template structure:

```
.gai/templates/               # project tier
  ├── summary.j2
  └── layout/
      └── base.j2

~/.config/gai/templates/      # user tier
  ├── summary.j2.md
  └── email/
      └── summary.j2
```

Resolution examples:

- `"summary"` → **Ambiguity error** (project tier has `summary.j2`, but which extension?)
- `"summary.j2"` → `.gai/templates/summary.j2` (explicit extension)
- `"layout/base"` → `.gai/templates/layout/base.j2` (path-specific, unique match)
- `"email/summary"` → `~/.config/gai/templates/email/summary.j2` (project tier has no matches, user tier has unique match)

## Using Named Templates

### In Configuration

Reference templates by logical name in your configuration:

```toml
# Use named templates (preferred)
system-instruction-template = "system/expert_analyst"
user-instruction-template = "prompts/analyze_document"

# Legacy literal templates still work (lower precedence)
# These are only used if the *-template keys are not set
system-instruction = "You are an expert analyst."
user-instruction = "Analyze this: {{ document }}"
```

### Precedence Between Named and Literal Templates

For each instruction type (system/user):

1. If `*-instruction-template` (logical name) is set: Use catalog-based resolution
2. Otherwise: Fall back to `*-instruction` (literal string or `@:file` reference)

This ensures named templates take precedence when both are configured.

### On Command Line

You can override templates via command-line config options:

```bash
# Use a different named template
gai generate --conf-user-instruction-template "prompts/summarize" --document @:report.txt

# Preview which template will be used
gai template render --conf-user-instruction-template "prompts/summarize" --document "test"
```

## Template Composition

The power of the template system comes from composing templates using Jinja2 features.

### Template Inheritance with `{% extends %}`

Create a base layout template and extend it:

**File:** `.gai/templates/layout/base_conversation.j2`
```jinja2
{# Base template for conversation-style prompts #}
You are {{ role | default("a helpful assistant") }}.

{% block task %}
{# Child templates override this block #}
{% endblock %}

{% if constraints %}
Constraints:
{% for constraint in constraints %}
- {{ constraint }}
{% endfor %}
{% endif %}
```

**File:** `.gai/templates/prompts/summarize.j2`
```jinja2
{% extends "layout/base_conversation" %}

{% block task %}
Please provide a concise summary of the following document:

{{ document }}

Focus on the key findings and main conclusions.
{% endblock %}
```

**Usage:**
```bash
gai generate \
  --conf-user-instruction-template "prompts/summarize" \
  --document @:report.txt \
  --role "technical analyst" \
  --constraints "Keep it under 200 words" \
  --constraints "Use bullet points"
```

### Including Reusable Components with `{% include %}`

Create reusable template snippets:

**File:** `.gai/templates/partials/output_format.j2`
```jinja2
Output format:
- Use markdown
- Include section headers
- Provide specific examples
```

**File:** `.gai/templates/prompts/analyze.j2`
```jinja2
Analyze the following document for key insights:

{{ document }}

{% include "partials/output_format" %}
```

### Importing Macros with `{% import %}`

Create reusable macros:

**File:** `.gai/templates/macros/formatting.j2`
```jinja2
{% macro code_block(language, code) %}
```{{ language }}
{{ code }}
```
{% endmacro %}

{% macro section(title, content) %}
## {{ title }}

{{ content }}
{% endmacro %}
```

**File:** `.gai/templates/prompts/code_review.j2`
```jinja2
{% import "macros/formatting" as fmt %}

Review this code:

{{ fmt.code_block(language, code) }}

{% if issues %}
{{ fmt.section("Known Issues", issues) }}
{% endif %}
```

## Best Practices

### Organizing Templates

Recommended directory structure:

```
.gai/templates/
├── layout/           # Base templates for inheritance
│   ├── base_conversation.j2
│   ├── base_analysis.j2
│   └── base_creative.j2
├── prompts/          # Specific prompt templates
│   ├── summarize.j2
│   ├── analyze.j2
│   ├── explain.j2
│   └── email/        # Grouped by domain
│       ├── formal.j2
│       └── friendly.j2
├── partials/         # Reusable snippets
│   ├── output_format.j2
│   ├── constraints.j2
│   └── examples.j2
└── macros/           # Reusable functions
    ├── formatting.j2
    └── validation.j2
```

### Avoiding Ambiguity

Follow these guidelines to prevent ambiguity errors:

1. **Use unique basenames when possible**:
   - ✅ Good: `summary.j2`, `detailed_analysis.j2`
   - ⚠️ Risky: `summary.j2`, `email/summary.j2` (requires path-specific names)

2. **Use subdirectories for disambiguation**:
   - When you have multiple templates with the same basename
   - Reference with path: `{% extends "email/summary" %}`

3. **Don't use multiple extensions for the same base name**:
   - ❌ Avoid: Both `summary.j2` and `summary.j2.md` in the same tier
   - ✅ Pick one: Either `summary.j2` or `summary.j2.md`

4. **Use project tier for project-specific overrides**:
   - Keep generic templates in user tier
   - Override specific ones in project tier
   - Project tier automatically takes precedence

### Naming Conventions

Recommended naming practices:

- **Use descriptive names**: `analyze_financial_report.j2` instead of `report.j2`
- **Use underscores for multi-word names**: `expert_system.j2` instead of `expertsystem.j2`
- **Group related templates**: Use subdirectories like `email/`, `code/`, `analysis/`
- **Prefix base templates**: Consider `base_` prefix for layout templates

### Template Design

- **Keep templates focused**: One template, one purpose
- **Use blocks for customization**: Define `{% block %}` regions in base templates
- **Document template variables**: Add comments explaining required/optional variables
- **Provide defaults**: Use `{{ variable | default("default value") }}` for optional variables
- **Extract common patterns**: Move repeated content to partials or macros

### Version Control

- **Commit template directories**: Add `.gai/templates/` to your repository
- **Document template changes**: Explain changes in commit messages
- **Share templates**: User templates can be shared across projects
- **Review template updates**: Templates affect AI behavior, so review changes carefully

## Troubleshooting

### TemplateNotFoundError

**Error message:**
```
TemplateNotFoundError: Template 'summary' not found.
Searched roots: ['/path/to/.gai/templates', '/home/user/.config/gai/templates']
```

**Solutions:**

1. Check that the template file exists in one of the searched roots
2. Verify the file has a recognized extension (`.j2` or `.j2.md`)
3. Check your `*-template-paths` configuration
4. Use `--debug` flag to see which roots are being scanned
5. Verify the logical name matches the file path (without extension)

### TemplateAmbiguityError

**Error message:**
```
TemplateAmbiguityError: Template name 'summary' is ambiguous in tier 'project'.
Candidates: [('summary.j2', '.j2'), ('email/summary.j2', '.j2')]
Use a more specific path or explicit extension.
```

**Solutions:**

1. **Use a path-specific name**: `{% extends "email/summary" %}` instead of `{% extends "summary" %}`
2. **Use an explicit extension**: `{% extends "summary.j2" %}` (if you have both `.j2` and `.j2.md`)
3. **Remove duplicate**: Remove or rename one of the templates
4. **Move to different tier**: Move one template to a different tier (e.g., project vs user)

### StrictUndefined Variable Errors

**Error message:**
```
TemplateError: 'document' is undefined
```

**Solutions:**

1. Make sure you're passing the variable: `--document "content"` or `--document @:file.txt`
2. Use a default value in the template: `{{ document | default("") }}`
3. Make variables optional: `{% if document %}...{% endif %}`
4. Check for typos in variable names

### Path Resolution Issues

If templates aren't being found:

1. Check if paths are being resolved correctly (relative vs absolute)
2. Use absolute paths in configuration temporarily to debug
3. Verify you're running from the expected working directory
4. Check if inside a Git repository (affects project path resolution)
5. Use `--debug` flag to see resolved paths

## CLI Commands for Working with Templates

The template system provides interactive commands for browsing and selecting templates. These commands reuse the same catalog and resolution logic described above.

### `gai template list`

**Purpose:** List all discovered templates in catalog order.

**Usage:**
```bash
# List all templates
gai template list

# List templates from a specific tier
gai template list --tier project

# Filter by substring in logical name
gai template list --filter summarize

# Output as JSON for machine consumption
gai template list --format json
```

**Example Table Output:**
```
TIER     LOGICAL NAME              RELATIVE PATH
project  layout/base_conversation  layout/base_conversation.j2
project  prompts/summarize         prompts/summarize.j2
user     summary                   summary.j2.md
user     email/formal              email/formal.j2
builtin  system/default            system/default.j2
```

**Example JSON Output:**
```bash
$ gai template list --format json
[
  {
    "logical_name": "layout/base_conversation",
    "tier": "project",
    "relative_path": "layout/base_conversation.j2",
    "absolute_path": "/full/path/.gai/templates/layout/base_conversation.j2",
    "root_index": 0,
    "extension": ".j2"
  },
  ...
]
```

**Key Features:**

- Single source of truth: Uses the same `discover_templates()` function as resolution
- Catalog ordering: Shows templates in the same precedence order used for resolution
- Displays both logical names and relative paths
- JSON format for scripting and tooling integration
- Helps users understand which template would be selected for a given name

### `gai template browse`

**Purpose:** Interactively browse and select templates using `fzf` with a preview pane.

**Usage:**
```bash
# Browse templates interactively (preview enabled by default)
gai template browse

# Browse and set as user instruction template
gai config set user-instruction-template "$(gai template browse)"

# Browse without preview pane
gai template browse --no-preview

# Browse only project templates
gai template browse --tier project

# Filter by substring before browsing
gai template browse --filter email
```

**Key Features:**

- Interactive selection: Uses `fzf` for fuzzy finding with keyboard navigation
- Preview enabled by default: Shows template content for the currently selected template
- Returns logical name: Output is the `logical_name_full` that can be used in configuration or templates
- Catalog-based: Uses the same template catalog as resolution
- Respects precedence: Templates are shown in the same order as they would be resolved
- Shell integration: Output only to stdout, making it easy to use in command substitution

**Requirements:**

- `fzf` must be installed and available on your PATH
- If `fzf` is not found, the command will fail with a clear error message

**Example Workflow:**
```bash
# Interactively select a template and configure it
gai config set user-instruction-template "$(gai template browse)"

# Browse project templates and see what's available
gai template browse --tier project

# Find a specific template by name
gai template browse --filter summary
```

### Implementation Principles

Both commands adhere to these principles:

1. **Single source of truth**: Call `discover_templates()` to build the catalog, not independent filesystem scans
2. **Consistent ordering**: Show templates in catalog order (tier precedence → root index → relative path)
3. **Round-tripping**: The logical name shown/returned is exactly what resolution would accept
4. **Reusable catalog**: The catalog built for listing/browsing is identical to the one used for resolution

This ensures that what users see in listing/browsing commands matches exactly how resolution works, maintaining a consistent mental model.

### Current Status

As of this writing:

- ✅ Template catalog and resolution system fully implemented
- ✅ Catalog discovery and ordering working as specified
- ✅ `gai template render` command exists for debugging templates
- ⏳ `gai template list` command not yet implemented
- ⏳ `gai template browse` command not yet implemented

The foundation is in place and the future commands can be added by building on the existing `template_catalog.py` and `templates.py` modules.

---

## References

- [Specification](../goals/templates/Specification.md) - Formal specification for template discovery and resolution
- [Strategy](../goals/templates/Strategy.md) - Implementation strategy and phase breakdown
- [README](../README.md) - General `gai` documentation and usage guide

## Contributing

When proposing changes to the template system:

1. Read the specification and strategy documents first
2. Maintain the strictness philosophy (fail loudly, don't guess)
3. Preserve the single source of truth principle (one catalog, many uses)
4. Update all three documentation sources (this doc, README, inline comments)
5. Add tests for new behaviors, especially error cases
