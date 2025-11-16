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
````jinja2
{% macro code_block(language, code) %}
```{{ language }}
{{ code }}
```
{% endmacro %}

{% macro section(title, content) %}
## {{ title }}

{{ content }}
{% endmacro %}
````

**File:** `.gai/templates/prompts/code_review.j2`
```jinja2
{% import "macros/formatting" as fmt %}

Review this code:

{{ fmt.code_block(language, code) }}

{% if issues %}
{{ fmt.section("Known Issues", issues) }}
{% endif %}
```

### Recursive Includes and Variable Sharing

Named templates fully support **recursive composition**: templates can include, extend, or import other templates, which can themselves include other templates, to any depth. All templates in the chain share the same variable context.

**How it works:**

- All `{% extends %}`, `{% include %}`, and `{% import %}` statements use the same catalog-based resolver
- Nested templates follow the same tier precedence and logical name resolution rules
- Variables passed to the top-level template are available in all included/extended templates
- The same Jinja environment and catalog are used throughout the rendering

**Example of three-level nesting:**

**File:** `.gai/templates/layout/base_conversation.j2`
```jinja2
You are {{ role }}.

{% block task %}
[base task]
{% endblock %}

{% block signature %}
-- End of instruction --
{% endblock %}
```

**File:** `.gai/templates/partials/greeting.j2`
```jinja2
Hello {{ username }}!
```

**File:** `.gai/templates/partials/output_format.j2`
```jinja2
Output format:
- variable: {{ important_var }}
- context: {{ context_var }}
```

**File:** `.gai/templates/prompts/nested_demo.j2`
```jinja2
{% extends "layout/base_conversation" %}

{% block task %}
{% include "partials/greeting" %}

Task details for {{ subject }}:
{% include "partials/output_format" %}
{% endblock %}
```

**Usage:**
```bash
gai template render \
  --conf-project-template-paths ".gai/templates" \
  --conf-user-instruction-template "prompts/nested_demo" \
  --role "assistant" \
  --username "Alice" \
  --subject "nested templates" \
  --important_var "VALUE" \
  --context_var "CONTEXT"
```

**Output:**
```
You are assistant.

Hello Alice!

Task details for nested templates:
Output format:
- variable: VALUE
- context: CONTEXT
-- End of instruction --
```

**Key points:**

- Variables like `role`, `username`, `subject`, `important_var`, and `context_var` are accessible in all templates
- The base template (`layout/base_conversation`) is extended
- Two partials (`greeting` and `output_format`) are included within the extended block
- All logical names use extensionless references and resolve via the catalog
- If any variable is missing, Jinja's `StrictUndefined` will raise a clear error

**Important notes for literal templates:**

Named templates (`*-instruction-template`) support recursive catalog-based composition. However, **literal templates** (`system-instruction` and `user-instruction` when provided as strings) do *not* use the template catalog. Literal templates:

- Are rendered using a simple string-based environment
- Cannot use `{% include %}` or `{% extends %}` to reference templates by logical name
- Should be used for simple, self-contained templates
- For composition, use named templates instead

### Variable Security and Template Injection Prevention

Template variables are always treated as **data, not code**. This is a critical security feature that prevents template injection attacks.

**How it works:**

When you pass a variable like `--subject 'Text with {{ var }}'`, the Jinja syntax in the variable value is rendered **literally**, not evaluated as a template expression.

**Example:**

```bash
gai template render \
  --conf-project-template-paths ".gai/templates" \
  --conf-user-instruction-template "simple" \
  --subject "Comparing {{ doc }} with the codebase" \
  --doc "requirements.md"
```

If the template is:
```jinja2
Subject: {{ subject }}
Document: {{ doc }}
```

The output will be:
```
Subject: Comparing {{ doc }} with the codebase
Document: requirements.md
```

Note that `{{ doc }}` appears **literally** in the subject line, not replaced with "requirements.md". This is intentional and correct.

**Why this matters:**

1. **Security**: Prevents malicious or accidental code injection via variable values
2. **Predictability**: Variables always render as the exact text you provide
3. **Safety**: Template code cannot be hidden in data from external sources (files, user input, etc.)

**If you want dynamic text in variables:**

If you need to construct variable values with dynamic content, do so **before** passing them to the template:

```bash
# Construct the value first
SUBJECT="Comparing ${DOC} with the codebase"

# Then pass the fully-formed string
gai template render \
  --conf-user-instruction-template "simple" \
  --subject "$SUBJECT" \
  --doc "requirements.md"
```

Or use the template itself to combine variables:

```jinja2
Subject: Comparing {{ doc }} with the codebase
Document: {{ doc }}
```

This ensures all template logic stays in template files where it can be reviewed and version-controlled.

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

### Nested Template Not Found

**Error message:**
```
TemplateError: Error rendering 'prompts/main' template: ...
  (nested) TemplateNotFound: partials/output_format
```

**Problem:** A template successfully loads, but an `{% include %}` or `{% extends %}` inside it fails to resolve a nested template.

**Solutions:**

1. **Verify the nested logical name**: The name used in `{% include "partials/output_format" %}` must exactly match the logical name (extensionless, with forward slashes)
   - Check file structure: Is it `.gai/templates/partials/output_format.j2`?
   - Verify no extra subdirectories or typos in the path

2. **Check extension mismatch**: If you have `output_format.j2.md` but reference `output_format.j2`, specify the correct extension or use extensionless names

3. **Ensure nested template is in the catalog**: Run `gai template list` to verify the nested template appears in the catalog

4. **Look for ambiguity**: If the nested template name is ambiguous in the same tier, you'll get an ambiguity error instead—use a more specific path

5. **Remember literal templates can't include from catalog**: If you're using `system-instruction` or `user-instruction` (not `*-instruction-template`), nested includes won't work because literal templates don't use the catalog

### Path Resolution Issues

If templates aren't being found:

1. Check if paths are being resolved correctly (relative vs absolute)
2. Use absolute paths in configuration temporarily to debug
3. Verify you're running from the expected working directory
4. Check if inside a Git repository (affects project path resolution)
5. Use `--debug` flag to see resolved paths

## I/O/C/M conventions and structured outputs

`gai` adopts a lightweight naming scheme so template authors can describe the intent of every variable without maintaining a separate schema file:

- **Inputs (`I_*`)** – Primary payload variables such as `I_document` or `I_topic`.
- **Controls (`C_*`)** – Knobs and stylistic levers like `C_style` or `C_format`.
- **Mechanisms (`M_*`)** – Supporting context such as `M_model` or `M_temperature`.
- **Outputs (`O_*`)** – Tag names that wrap the interesting parts of the response, e.g. `<O_main>...</O_main>`.

When you run `gai generate --document foo.md`, the CLI still provides the raw `document` variable, but it also injects `I_document` and `C_document` automatically so templates can opt-in to the convention incrementally. The `gai template inspect <logical_name>` command uses Jinja's `meta` API plus tag scanning to infer which variables a template references and which `<O_*>` tags it emits. You can browse a high-level summary inline by running `gai template list --interface`.

On the output side, the generator can now extract a single tagged channel without manual `awk` incantations:

```bash
gai generate --capture-tag O_main --output-file summary.md --document @:report.md
```

`--capture-tag` buffers the streaming response, finds the first `<O_main>...</O_main>` block, and either prints it or writes it to `--output-file`. This makes it easy to build shell pipelines that consume only the structured portion of a longer reply.

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

# Include inferred interfaces
gai template list --interface
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
- Optional `--interface` flag runs the interface inspector and adds I/O/C/M/outputs to the listing

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

### `gai template inspect`

**Purpose:** Reveal the inferred inputs, controls, mechanisms, and outputs for a single template.

**Usage:**
```bash
gai template inspect prompts/summarize
```

**Key Features:**

- Uses the same catalog and strict resolution rules as rendering commands
- Runs Jinja's meta analysis to list undeclared `I_*`, `C_*`, and `M_*` variables
- Scans the template source for `<O_*>` tags so you know which outputs exist
- Prints CLI flag hints for every input/control (`I_document → --document`)

**Sample Output:**
```
Template: prompts/summarize

Inputs (I_*, available via CLI flags):
  I_document  (CLI: --document)

Controls (C_*, available via CLI flags):
  C_style  (CLI: --style)

Mechanisms (M_*):
  M_model

Outputs (O_* tags):
  O_main

Other variables:
  helper_block
```

Use this command to learn what to pass before running `gai generate`, to audit template design, or to decide which tag to capture with `gai generate --capture-tag`.

### Implementation Principles

Both commands adhere to these principles:

1. **Single source of truth**: Call `discover_templates()` to build the catalog, not independent filesystem scans
2. **Consistent ordering**: Show templates in catalog order (tier precedence → root index → relative path)
3. **Round-tripping**: The logical name shown/returned is exactly what resolution would accept
4. **Reusable catalog**: The catalog built for listing/browsing is identical to the one used for resolution

This ensures that what users see in listing/browsing commands matches exactly how resolution works, maintaining a consistent mental model.

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
