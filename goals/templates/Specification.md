## 1. Goals

1. Provide a deterministic and inspectable way to discover all available templates, ordered according to configuration and “distance” to the current project.
2. Allow templates to refer to each other using stable logical names (Obsidian-style), independent of physical file extensions.
3. Ensure correctness over convenience: any ambiguity (homonymy) in the “closest” tier is treated as an error, not silently auto-resolved.
4. Reuse the same discovery and ordering logic for:

   * resolving `{% extends %}`, `{% include %}`, `{% import %}`; and
   * future CLI commands that list, browse, and select templates (for example using `fzf` with an ordered list and a preview pane).

---

## 2. Concepts and terminology

The specification introduces the following core concepts.

1. **Template root**
   A directory that is searched for template files. Examples:

   * project root templates, e.g. `<project>/.gai/templates`
   * user root templates, e.g. `~/.config/gai/templates`
   * builtin root templates, e.g. a directory packaged inside `gai`.

2. **Tier**
   A named group of template roots with a defined precedence. The initial tiers are:

   * `project` tier: roots that are considered closest to the current repository or working directory.
   * `user` tier: user-level roots, typically under the home directory.
   * `builtin` tier: read-only templates that ship with the tool.

   Tiers are totally ordered, for example: `project` > `user` > `builtin`.

3. **Template file**
   A physical file under a template root whose extension is one of the recognised template extensions. Initially:

   * recognised extensions: `.j2`, `.j2.md`
   * one file = one template.

4. **Logical template name**
   The string that appears inside Jinja `{% extends %}`, `{% include %}`, and `{% import %}` statements, and the string used in configuration keys like `user-instruction-template`.

   * Logical names are extensionless by default (for example `layout/base_conversation`, `summary`, `partials/header`).
   * They are interpreted relative to template roots according to the rules in section 4.
   * A logical name may optionally include an explicit extension (for example `layout/base_conversation.j2`) to force selection of a specific file, but this is considered an advanced and less ergonomic form.

5. **Template catalog**
   A data structure produced by discovery that represents all known template files, enriched with metadata and ordered according to the precedence rules. This catalog is the single source of truth used for resolution and listing.

---

## 3. Configuration model

The configuration must provide enough information to discover and order template roots. The specification assumes three fixed tiers for now, with explicit configuration keys:

* `project-template-paths`: list of paths for the `project` tier.
* `user-template-paths`: list of paths for the `user` tier.
* `builtin-template-paths`: list of paths for the `builtin` tier (optional; may be implicit if packaged).

### 3.1. Tier ordering

The global precedence order of tiers is fixed and documented:

1. `project`
2. `user`
3. `builtin`

Higher tiers override lower tiers when resolving a logical name. Within a tier, all roots are considered at the same “distance” and will be scanned together.

### 3.2. Path semantics

For each tier:

* Each path in the corresponding `*-template-paths` list is a directory that may contain templates.
* Paths may be absolute or relative:

  * relative paths are resolved against the current working directory or repository root (the exact rule should be defined in the implementation spec, but the catalog must see only resolved absolute paths).
* Paths that do not exist are ignored, but this should be logged at debug/info level.

---

## 4. Template discovery and catalog specification

Discovery is the process of scanning template roots to build a template catalog. This catalog must be reusable across:

* name resolution for Jinja, and
* CLI commands that list or browse templates.

### 4.1. Inputs

Discovery takes as input:

1. the resolved and ordered list of tiers;
2. for each tier, the list of resolved template root directories;
3. the set of allowed template extensions.

### 4.2. Template record

Discovery produces a list (or equivalent collection) of **template records**, each with at least the following fields:

* `logical_name_full`: the canonical logical name derived from the path, without extension, for example:

  * `layout/base_conversation` for `.../layout/base_conversation.j2`
  * `summary` for `.../summary.j2.md`
* `relative_path`: the path relative to its root, including extension, for example `layout/base_conversation.j2`.
* `absolute_path`: the absolute filesystem path.
* `tier`: one of `project`, `user`, `builtin`.
* `root_index`: the zero-based index of the root within its tier.
* `extension`: the file extension, including the dot, for example `.j2`, `.j2.md`.

Additional metadata may be added later (for example file size, last modified time).

### 4.3. Discovery algorithm

For each tier in precedence order (`project`, `user`, `builtin`):

1. For each root in the tier, in configuration order (list order):

   1. If the root directory does not exist, skip it.
   2. Recursively walk the directory (for example using `rglob("*")`).
   3. For each file encountered:

      * If the file is not a regular file, skip it.
      * If the file extension is not in the allowed extension set, skip it.
      * Compute `relative_path` as the path relative to the root.
      * Compute `logical_name_full` by removing the extension from `relative_path` and normalising separators to `/`.
      * Create a template record and add it to the catalog.

### 4.4. Catalog ordering

The primary catalog ordering is:

1. by `tier` precedence: `project` templates before `user`, then `builtin`;
2. within a tier, by `root_index` (order of roots in configuration);
3. within a root, by `relative_path` in lexicographical order.

This ordering must be stable and deterministic. It is the default order used:

* when presenting templates in listing or browsing commands; and
* when iterating candidates during name resolution.

This means that the list a user sees in an `fzf`-based selector is exactly the same order that the resolver conceptually uses when searching, so the mental model stays consistent.

---

## 5. Logical name resolution specification

Resolution is the process of mapping a logical template name (for example `"summary"` or `"layout/base_conversation"`) to exactly one template record from the catalog.

The resolver must obey two core invariants:

1. It only considers template records from the catalog built according to this specification.
2. For any logical name, at most one template record at the “closest non-ambiguous tier” is considered valid. Any ambiguity at that tier is a hard error.

### 5.1. Inputs

The resolver takes:

* the template catalog; and
* a logical name string `name` (as used in templates or config).

### 5.2. Explicit-extension rule

If `name` ends with one of the known extensions (for example `.j2` or `.j2.md`), then:

* strip the extension to obtain `base_name`; and
* record the explicit extension as `required_extension`.

In this case, resolution will only consider template records whose `logical_name_full` equals `base_name` and whose `extension` equals `required_extension`.

If `name` does not end with a known extension, then `required_extension` is `None` and extension ambiguity will be handled as described in section 5.5.

### 5.3. Path-specific versus basename-only names

If `name` contains a `/` character, it is treated as a path-specific name. Otherwise it is treated as a basename-only name.

1. **Path-specific name** (for example `"layout/base_conversation"`):

   * A template record matches if:

     * `logical_name_full` equals `base_name` (string exact match), and
     * either `required_extension` is `None` or `extension` equals `required_extension`.

2. **Basename-only name** (for example `"summary"`):

   * A template record matches if:

     * `logical_name_full`’s last path segment (its basename) equals `base_name`, and
     * either `required_extension` is `None` or `extension` equals `required_extension`.

This distinction is what allows the “shortest unambiguous name” behaviour: users can start with `summary` and, if collisions appear, disambiguate by writing `email/summary` or similar.

### 5.4. Tier-aware matching

Resolution proceeds tier by tier, using the global tier precedence:

For each tier in order:

1. Build the list `tier_candidates` of template records in that tier that match `name` according to section 5.3 (and 5.2 for explicit extension).
2. If `tier_candidates` is empty, continue to the next tier.
3. If `tier_candidates` contains exactly one record, return that record as the resolution result and stop.
4. If `tier_candidates` contains more than one record, raise an *ambiguity error* (see section 6.2) and stop. Do not look at lower tiers.

If all tiers are processed without finding any candidate, the resolver raises a *template not found* error (section 6.1).

### 5.5. Extension ambiguity policy

If `required_extension` is `None` and multiple records differ only by extension at the same `logical_name_full` and tier, then this is treated as an ambiguity.

Example:

* two template records in the project tier:

  * `logical_name_full = "summary"`, `extension = ".j2"`
  * `logical_name_full = "summary"`, `extension = ".j2.md"`
* user writes `{% extends "summary" %}`.

This triggers an ambiguity error. The user may resolve it by:

* using an explicit extension (`"summary.j2"` or `"summary.j2.md"`), or
* removing one of the files, or
* moving one of the files and using a path-specific name.

This strictness matches the philosophy used for undefined variables: ambiguous situations do not silently pick an arbitrary candidate.

---

## 6. Error semantics

The system distinguishes three main classes of error when resolving a logical name.

### 6.1. Template not found

Condition:

* For all tiers, the candidates list is empty.

Effect:

* Raise a `TemplateNotFound` error (or a tool-specific equivalent) with at least:

  * the logical name passed in;
  * a summary of the template roots that were searched.

This error is considered recoverable by the user by:

* checking their configuration; or
* adjusting the name or adding the missing template.

### 6.2. Ambiguous name in tier

Condition:

* There exists a tier for which:

  * the candidates list is non-empty; and
  * its length is strictly greater than one.

Effect:

* Raise a `TemplateAmbiguityError` (or equivalent) that includes:

  * the logical name;
  * the tier where the ambiguity occurred;
  * the list of candidate records (at least relative paths and extensions);
  * a hint that the user should specify a more specific name (for example `path/name`) or explicit extension.

The resolver must not fall back to a lower tier in this case. The ambiguity is considered fatal.

### 6.3. Invalid logical name syntax

If the logical name string contains characters or patterns that the implementation decides to reject (for example absolute paths starting with `/`, path traversal patterns like `../` if you choose to forbid them), resolution fails with a specific “invalid template name” error, before any filesystem interaction.

The exact rules for valid names can be detailed in the implementation spec, but the discovery and resolution spec assumes names are normalised and safe.

---

## 7. Interaction with listing and browsing commands

Future CLI commands such as `gai template list` or `gai template browse` must be defined in terms of the template catalog.

Key requirements:

1. **Single source of truth**
   Listing commands must call the same discovery function that builds the catalog for resolution. They must not independently scan the filesystem in a different way.

2. **Ordering**
   When listing templates (for example piping into `fzf`), the order shown to the user must be exactly:

   * by `tier` (project, user, builtin),
   * then by `root_index`,
   * then by `relative_path`.

   This gives users a visible representation of the resolution precedence.

3. **Displayed identifier**
   Each entry in a template list should be identified using at least:

   * the `logical_name_full`; and
   * the `tier` and `relative_path`.

   For example, a line could look like:

   * `project  layout/base_conversation  (.gai/templates/layout/base_conversation.j2)`
   * `user     summary                   (~/.config/gai/templates/summary.j2.md)`

   The exact formatting belongs in the CLI specification, but the principle is that users see both the logical name and the physical location.

4. **Preview**
   When integrating with `fzf` or similar tools, the preview pane should show the contents of the `absolute_path` of the currently selected template record. This is possible because the catalog holds the physical path.

5. **Round-tripping**
   When an interactive command returns a selected template to the caller (for example when the user chooses a template for `system-instruction-template`), it should return the logical name that corresponds to `logical_name_full`. This ensures that what the user chooses visually is exactly what will be used later by the resolver.

---

## 8. Backwards compatibility considerations (high level)

The specification assumes that in addition to named templates, there will still be support for:

* literal templates in configuration (`system-instruction`, `user-instruction`); and
* `@:path` syntax for loading template content from arbitrary files.

At the specification level:

* literal and `@:path` templates are treated as standalone strings that are rendered using `Environment.from_string`, not via the loader and catalog;
* composition (extends, include, import) is only guaranteed to be correct and well defined when using named templates that go through this catalog and resolution process.

Precedence rules between the two worlds (literal versus named) are part of the implementation strategy, but the key invariant is:

> Whenever a `*-instruction-template` logical name is used, it must be resolved via the catalog and name resolution described above.

---

This should give you a solid, coherent specification that an agent can implement step by step without inventing its own rules, and that you can later reuse directly when you design the CLI subcommands for listing and browsing templates.
