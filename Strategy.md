# Strategy for implementing I/O/C/M conventions and UX improvements in gai

> This document is intended to be read and executed by an LLM agent working on the `gai` repository. It is designed to be self-contained: it restates all the relevant context and desired changes from the prior discussion so that the agent does not need any external conversation history.

## 1. Context and current state

### 1.1. Project overview

The `gai` project is a command-line tool for working with Google Gemini / GenAI. It focuses on:

- a flexible CLI (`gai`) with subcommands: `generate`, `config`, `template`;
- a Jinja2-based template system with tiered template roots (project, user, builtin);
- configuration layering and a `--conf-<name>` mechanism for overriding config via CLI;
- structured error handling and streaming generation.

Relevant files (non-exhaustive):

- `src/gai/__main__.py` – main entry point.
- `src/gai/cli.py` – CLI parsing and subcommand handlers.
- `src/gai/config.py` – configuration, including template root resolution.
- `src/gai/config_model.py` – type-safe config object.
- `src/gai/exceptions.py` – exception hierarchy.
- `src/gai/generation.py` – interaction with GenAI API and streaming output.
- `src/gai/template_catalog.py` – template discovery and catalog.
- `src/gai/templates.py` – Jinja environment, template rendering, catalog-based loader.
- `docs/templates.md` – detailed template system documentation.
- `README.md` – top-level overview and usage.

The template system already supports:

- discovery of template files under configured roots and tiers (`project`, `user`, `builtin`);
- logical template names (extensionless, with `/` separators) for use in `{% extends %}`, `{% include %}`, `{% import %}` and config keys;
- a catalog (`TemplateCatalog` + `TemplateRecord`) that feeds Jinja’s `BaseLoader` to resolve template names in a tier-aware way;
- strict resolution (ambiguity errors instead of silently picking one of several matches).

CLI support around templates includes:

- `gai template render` – render system and user instruction, with `--part` for system/user/both;
- `gai template list` – list discovered templates (table or JSON);
- `gai template browse` – fzf-based interactive selector that returns a logical name.

### 1.2. Current usage patterns and pain points

From the user’s perspective, the following issues and idioms have emerged:

1. **Hidden template parameters**  
   Because templates can `extends` / `include` / `import` other templates, the set of “inputs” that a template needs (parameters passed via `--foo` CLI flags) is not obvious. To know what a template needs, one must read several files.

2. **Manual structured output extraction**  
   A common idiom is to instruct the LLM to wrap the relevant answer in XML-style tags in the template:

   ```jinja2
   <output>
   ...answer...
   </output>
````

and then extract this answer via shell tools:

```sh
gai ... | awk '/<output>/{f=1; next} /<\/output>/{f=0} f' > "$outfile"
```

This is powerful but non-discoverable and somewhat clumsy.

3. **Long and frequently used `--conf-*` flags**
   The most frequently used configuration override is:

   ```sh
   gai template render --conf-user-instruction-template some_template ...
   ```

   This is “fucking painful” to type, especially for routine experimentation. The user wants something more ergonomic (shorter flags, positional arguments).

4. **Lack of explicit input/output semantics**
   Conceptually, prompts have inputs and outputs; and in an IDEF0 framing also controls and mechanisms. The current system treats all template variables uniformly; there is no explicit notion of “this variable is input”, “this is a control”, etc. That makes it harder to document, inspect, and eventually compose templates (e.g., in pipelines).

### 1.3. Existing design philosophy and constraints

* The project favors **correctness over convenience**: ambiguous template names produce errors; missing variables are handled by `StrictUndefined`.
* Template system is built around a single catalog that is the **single source of truth** for discovery and resolution.
* Templates and config are distinct:

  * Named templates come from the catalog via `*-instruction-template` config keys.
  * Literal templates are provided via `*-instruction` and rendered with `render_template_string`.
* Configuration layering is already robust; new features should respect existing precedence rules.
* The user prefers **prose over telegraphic style** in documentation, and **sentence case** for headings.

### 1.4. Testing constraint

The user explicitly requested: **always separate tests from code**.

For the LLM agent, this means:

* do not add tests inside production modules (no inline asserts or test harnesses);
* add tests as separate modules under a `tests/` directory (for example `tests/test_templates_iocm.py`, `tests/test_cli_capture_tag.py`, etc.);
* keep test-related code and fixtures out of `src/` modules.

If the `tests/` directory does not exist, the agent should create it.

---

## 2. High-level goals of this strategy

The strategy should guide the implementation of the following changes:

1. **Introduce an implicit I/O/C/M convention for template variables and output markers**, based on naming prefixes, to approximate an IDEF0 style classification without explicit schema files.

2. **Leverage Jinja2 introspection and conventions to infer and expose template “interfaces”** (inputs, outputs, controls, mechanisms) without duplicating information in separate metadata blocks.

3. **Improve CLI ergonomics** for working with user instruction templates:

   * shorter flags and positional template name for `gai template render`;
   * high-level shorthands where appropriate.

4. **Add first-class support for structured output extraction** based on template conventions:

   * built-in `generate` options to capture the content between specific tags;
   * ability to tie those tags to template-declared outputs.

5. **Update documentation** (`README.md`, `docs/templates.md`, and possibly new or updated strategy/specification docs) to reflect the new conventions, commands, and workflow.

6. **Maintain and extend tests** in a clean, separate test suite, ensuring behavior is validated and regressions are caught.

The strategy is organized into phases and concrete tasks. The LLM agent should follow the phases in order, but can refine or reorder sub-steps as long as dependencies are respected.

---

## 3. I/O/C/M naming convention design

### 3.1. Basic naming scheme

Use a prefix-based convention on template variable and marker names to classify them into IDEF0-like categories:

* **Inputs**: variables whose names start with `I_` (for example `I_document`, `I_topic`).
* **Outputs**: output channels whose names start with `O_` (for example `O_main`, `O_outline`), used primarily in tags in the generated text.
* **Controls**: variables with names starting with `C_` (for example `C_style`, `C_audience`), representing knobs that shape behavior but are not the main payload.
* **Mechanisms**: variables or config keys with names starting with `M_` (for example `M_model`, `M_temperature`), representing underlying tools and resources.

Important notes:

* Template authors will write `I_document` and `C_style` in Jinja; they do not have to change the CLI interface (see mapping in section 4).
* The prefixes are purely a convention within template names and tags; they do not affect Jinja’s syntax rules.

### 3.2. Mapping CLI variables to I/O/C/M names

To avoid forcing users to type `--I_document`, introduce automatic mapping in the CLI:

* When parsing template variables from CLI arguments (currently done in `parse_template_args_from_list`), for each `--name value`:

  * store the variable as `template_vars[name] = value` as today;
  * additionally, if the template’s declared interface contains an `I_name`, add `template_vars["I_" + name] = value`;
  * similarly, if there is a `C_name` in the template, map `--name` to `C_name` as well.

This requires:

* being able to know, for a given template, whether there are `I_*` or `C_*` variables with a given base name (requires introspection or caching of interface data); or
* using a simpler first version: always map `--name` to both `I_name` and `C_name` alongside `name`, and rely on `StrictUndefined` and actual usage to determine what is needed.

The strategy suggests starting with the simple mapping:

* `--document` → `document` and `I_document`;
* `--style` → `style` and `C_style`;

and possibly tightening it later once interface extraction exists.

### 3.3. Output tagging convention

For outputs, reuse the user’s existing pattern of wrapping the “interesting” part of the answer in tags, but with names following the `O_` convention.

To make it structured:

* adopt tags like `<O_main>…</O_main>` and `<O_outline>…</O_outline>`, where `O_main` and `O_outline` are the channel names;
* encourage template authors to use a small macro to emit these tags (this macro can live in a reusable `macros` template):

  ```jinja2
  {# macros/gai_io.j2 #}
  {% macro output_block(name) -%}
  <{{ name }}>
  {{ caller() }}
  ```

</{{ name }}>
{%- endmacro %}

````

Usage in templates:

```jinja2
{% import "macros/gai_io" as io %}

{% call io.output_block("O_main") %}
Here is the main answer...
{% endcall %}
````

Internally, `gai` will:

* treat tag names starting with `O_` as output channels;
* allow CLI commands to extract the text between those tags (see section 5).

### 3.4. Possible future extensions

This strategy does not require these, but allows for later enhancements:

* using suffixes for required vs optional (`I_document_req`, `I_topic_opt`);
* encoding lightweight type hints in names (`I_items__list`, `I_document__text`);
* documenting idioms for how to treat controls vs mechanisms at the config level.

For now, do not implement suffix semantics; focus on getting prefix-based classification working and observable.

---

## 4. Template interface extraction and inspection

### 4.1. Goals

Provide a way to answer, from the CLI and programmatically:

* What does this template *need* (inputs, controls, mechanisms)?
* What outputs (if any) does this template declare?

Do this **without** introducing a separate schema file that duplicates information already present in templates.

### 4.2. Using Jinja’s meta API

Leverage Jinja’s `meta` module to extract undeclared variables from templates:

* For a given template (logical name):

  1. Build the catalog (as is already done in `render_system_instruction` and `render_user_instruction`) via `get_template_roots` and `discover_templates`.
  2. Build a `jinja2.Environment` with the `CatalogLoader`.
  3. Load the template source from the resolved `TemplateRecord`’s `absolute_path`.
  4. Parse the source into an AST via `env.parse(source)`.
  5. Use `jinja2.meta.find_undeclared_variables(ast)` to get the set of variable names that the template references but does not define itself.

Important: this only covers the top-level template file. For more accurate introspection, you have two options:

* inspect only the top-level template and accept that includes may introduce additional parameters (simpler); or
* attempt to recursively inspect included/extended templates by scanning for `{% extends %}` and `{% include %}` and repeating the process.

The strategy recommends starting with top-level inspection (low complexity, already useful), and later considering deep introspection if necessary.

### 4.3. Partitioning variables using prefixes

Given the set of undeclared variables `vars_`:

* classify them into categories based on prefixes:

  * `inputs = {v for v in vars_ if v.startswith("I_")}`;
  * `controls = {v for v in vars_ if v.startswith("C_")}`;
  * `mechanisms = {v for v in vars_ if v.startswith("M_")}`;
  * other variables remain unclassified (they might be things like `role` or derived names).

* for outputs, do not rely on variables; rely on tag names (see next section).

When presenting the interface, show both the full prefixed names and the inferred base names:

* `I_document` → base name `document`, CLI flag `--document`;
* `C_style` → base name `style`, CLI flag `--style`.

### 4.4. Discovering outputs from tags

Output channels are not variables; they are tag names in the generated text. There are two possible ways to introspect them from the template source:

1. **Scan the raw source for `<O_...>` tags**
   Pros: simple string search or regex; no need to interpret the template AST.
   Cons: might pick up tags generated via variables or macros only at runtime.

2. **Scan for macro usage with literal channel names**
   If the `output_block` macro is used consistently with literal channel names, you can search the AST for macro calls and extract the first argument when it is a literal.

For the initial implementation, scanning the source text for `<O_...>` and `</O_...>` patterns is sufficient. For example, use a regex like:

```python
re.findall(r"<(O_[A-Za-z0-9_]+)>", source)
```

and deduplicate.

This will give a set of output channel names (for example `{"O_main", "O_outline"}`) that can be surfaced in `template inspect` and used by CLI capture options.

### 4.5. New helper API for template interface

Introduce a small internal representation, e.g.:

```python
@dataclass
class TemplateInterface:
    logical_name: str
    inputs: dict[str, str]        # full_name -> base_name
    controls: dict[str, str]
    mechanisms: dict[str, str]
    outputs: set[str]             # e.g. {"O_main", "O_outline"}
```

and a function, perhaps in a new module `src/gai/template_interface.py`, to build this:

```python
def build_template_interface(config: dict[str, Any], logical_name: str) -> TemplateInterface:
    ...
```

This function should:

* resolve the template via the catalog, as described above;
* extract undeclared vars, partition by prefixes, compute base names;
* scan the source text for output tags starting with `O_`.

**Important:** this is purely introspection; it does not alter template rendering.

### 4.6. CLI support: `gai template inspect`

Add a new subcommand:

* `gai template inspect <logical_name> [options]`

Behavior:

* loads effective config (as other template commands do);
* builds the template interface for the given logical name;
* prints a human-readable summary to stdout, for example:

  ```text
  Template: prompts/summarize

  Inputs (I_*, available via CLI flags):
    I_document  (CLI: --document)
    I_topic     (CLI: --topic)

  Controls (C_*, via CLI flags):
    C_style     (CLI: --style)

  Mechanisms (M_*):
    M_model
    M_temperature

  Outputs (O_* tags):
    O_main
  ```

Options (can be extended later):

* none are strictly required for v1; you may consider `--format json` as a future enhancement, but keep v1 simple.

### 4.7. CLI enhancement: `gai template list --interface`

Extend `gai template list` to optionally include a minimal interface summary per template when a flag is provided:

* e.g., `gai template list --interface` could show an additional column for a comma-separated list of input base names (`document, topic`);
* implement this with caution: introspection may be somewhat expensive if called for every record; consider:

  * limiting `--interface` to smaller sets (via `--tier` or `--filter`);
  * or caching interfaces in memory for the duration of the command.

---

## 5. Output capture in `gai generate`

### 5.1. Goals and user story

The user currently writes:

```sh
gai ... | awk '/<output>/{f=1; next} /<\/output>/{f=0} f' > "$outfile"
```

We want to:

* make this idiom first-class, discoverable, and less error-prone;
* let users specify which tag or output channel to capture;
* eventually tie this to the outputs declared by templates (`O_*` tags).

### 5.2. New `generate` options

Add options to `gai generate`:

1. `--capture-tag TAGNAME`

   * Example: `--capture-tag O_main` or `--capture-tag output`.
   * Semantics: after the streaming response is complete, extract the content between `<TAGNAME>` and `</TAGNAME>` (first or last occurrence; choose one and document it, and write tests).

2. `--capture-output OUTPUT_NAME` (optional, can be added later)

   * Example: `--capture-output main`.
   * Semantics: find `<O_main>...</O_main>` by constructing `O_` + `OUTPUT_NAME`, so users do not need to remember the full tag.

3. `--output-file PATH` (optional but very convenient)

   * If provided, write the captured text to this file instead of stdout.
   * If not provided, print the captured content to stdout.

Initially, implement `--capture-tag` and `--output-file`. `--capture-output` can be an extra convenience where you prepend `O_`.

### 5.3. Implementation outline

#### 5.3.1. Adjust generation to support post-processing

Currently `generate` in `src/gai/generation.py` streams output directly to stdout via `stream_output`.

To support capture:

* add optional parameters to `generate` (or to a lower-level helper):

  * `capture_tag: Optional[str] = None`
  * `output_file: Optional[str] = None`

* decide on a clear behavior:

  * if `capture_tag` is `None`, keep current behavior: stream to stdout as text arrives;
  * if `capture_tag` is not `None`, buffer the entire text instead of writing each chunk immediately, then post-process.

Implementation idea:

* Instead of `stream_output(stream_generator)`, introduce:

  ```python
  def collect_output(stream_generator) -> str:
      text_parts = []
      for chunk in stream_generator:
          if chunk.text:
              text_parts.append(chunk.text)
              # optionally still echo to stdout if capture is "in addition", but
              # to match the awk idiom, default should be: do not print full text.
      return "".join(text_parts)
  ```

* Then, in `generate`:

  ```python
  if capture_tag:
      full_text = collect_output(stream_generator)
      captured = extract_between_tags(full_text, capture_tag)
      if output_file:
          write_to_file(output_file, captured)
      else:
          print(captured, end="" if captured.endswith("\n") else "\n")
  else:
      stream_output(stream_generator)  # existing behavior
  ```

The helper `extract_between_tags` should:

* find the first occurrence of `<TAG>` and `</TAG>`;
* extract the text between them;
* be robust to missing tags (raise `GenerationError` or print a clear message and exit with non-zero status).

#### 5.3.2. Integrate new options into the CLI

In `src/gai/cli.py`, inside `create_parser`:

* for the `generate` subparser, add new arguments:

  ```python
  generate_parser.add_argument(
      "--capture-tag",
      metavar="TAG",
      help="Capture only the text between <TAG> and </TAG> in the response",
  )
  generate_parser.add_argument(
      "--output-file",
      metavar="PATH",
      help="Write captured output to PATH instead of stdout (requires --capture-tag)",
  )
  ```

In `_handle_new_cli` (`src/gai/__main__.py`):

* when calling `generate(effective_config, template_vars)`, pass through `parsed.capture_tag` and `parsed.output_file` (adjust function signature accordingly).

Ensure backward compatibility:

* if `capture_tag` is not provided, default to current streaming behavior;
* if `output_file` is given without `capture_tag`, either treat it as error, or document that it is only meaningful with `--capture-tag` and enforce that.

### 5.4. Optional integration with template interface

Once `TemplateInterface.outputs` exists:

* optionally add `--capture-main` that:

  * resolves the user template in use;
  * retrieves its outputs (e.g. `{"O_main", "O_outline"}`);
  * if there is a single output channel, or a convention that `O_main` is the primary one, maps `--capture-main` to `--capture-tag O_main`.

This is an enhancement and can be added after the basic `--capture-tag` is working. If added, remember to:

* document the behavior;
* add tests that verify correct fallback when multiple outputs exist.

---

## 6. CLI ergonomics for user instruction templates

### 6.1. Goals

Reduce friction when working with user instruction templates, specifically:

* avoid typing `--conf-user-instruction-template` constantly;
* support a natural, positional template name argument for `gai template render`.

### 6.2. Short flag aliases

Introduce short and readable aliases for common config keys:

* `-t` / `--template` → sets `user-instruction-template` (equivalent to `--conf-user-instruction-template`);
* optionally `-s` / `--system-template` for `system-instruction-template`.

Implementation:

* In `create_parser`, for the `template render` parser (and possibly others that need it):

  ```python
  render_parser.add_argument(
      "-t",
      "--template",
      metavar="LOGICAL_NAME",
      help="User instruction template logical name (shortcut for --conf-user-instruction-template)",
  )
  ```

* After parsing arguments in `_handle_new_cli`, before calling `load_effective_config(args_list)`, you have two options:

  1. adjust the `args_list` to insert a synthetic `--conf-user-instruction-template` argument; or
  2. pass an extra “overlay” dict to `load_effective_config`.

Given the existing design, the simplest is to mutate `args_list` before calling `load_effective_config`:

* detect if `--template` or `-t` is present in `parsed`;
* if so, insert `--conf-user-instruction-template` and its value into `args_list` in place of `--template`;
* this keeps all config handling in one place.

### 6.3. Positional template name for `template render`

Make `gai template render` support:

```sh
gai template render prompts/summarize --document @:foo.md
```

where `prompts/summarize` is taken as the user instruction template logical name.

Implementation in `create_parser`:

* add a positional argument to the `render_parser`:

  ```python
  render_parser.add_argument(
      "template_name",
      nargs="?",
      help="Optional user instruction template logical name (equivalent to -t NAME)",
  )
  ```

In `_handle_new_cli`:

* when `parsed.command == "template"` and `parsed.template_command == "render"`:

  * if `parsed.template_name` is set and `--template` / `-t` / `--conf-user-instruction-template` are not already provided, treat `template_name` as the chosen template;
  * convert this to the same config override as in 6.2 (mutating `args_list`).

Semantics:

* if no `template_name` and no `--template` / `--conf-user-instruction-template` are provided, `render` uses the configured default template (from config);
* if `template_name` is provided, it overrides the default for this invocation only.

### 6.4. Optional shorthand subcommand for user templates

Optionally introduce a shorthand for a common pattern:

* `gai u <template> [vars...]` → shorthand for `gai template render --part user -t <template> [vars...]`.

This is not strictly necessary to achieve the user’s core goals but may be convenient. If implemented:

* add a `u` subcommand to the main parser with minimal flags;
* forward it internally to the `template render` logic with `part="user"` set.

If time is constrained, this can be deferred.

---

## 7. Documentation updates

The LLM agent must **update documentation** to reflect new conventions and features. At minimum:

### 7.1. README.md

Add a section that:

* explains the new CLI options (`--capture-tag`, `--output-file`, `-t/--template`, positional template name for `template render`);

* contains an example showing how to replace the old `awk` pipeline:

  ```sh
  # Old pattern:
  gai generate -t prompts/summarize --document @:foo.md | awk '/<output>/{...}' > summary.md

  # New pattern:
  gai generate -t prompts/summarize --capture-tag O_main --output-file summary.md
  ```

* briefly introduces the I/O/C/M naming convention, with a short example template showing `I_document` and `<O_main>...</O_main>`.

Ensure headings follow sentence case and prose is not overly telegraphic.

### 7.2. docs/templates.md

Update or extend this document to:

* describe the I/O/C/M naming convention:

  * how to use `I_*`, `C_*`, `M_*` inside templates;
  * how to mark outputs with `O_*` tags and the optional `output_block` macro;
* describe the new `gai template inspect` command:

  * show example output;
  * explain how it infers interface information from template code (no separate schema to maintain);
* describe any changes to `gai template list` (if `--interface` was added);
* include a section on structured output extraction:

  * how `--capture-tag` works;
  * how to tie it to `O_*` tags.

Keep the narrative consistent with the existing design philosophy: correctness, catalog as single source of truth, etc.

### 7.3. New or updated design documents

If there is an existing templates specification or strategy file referred to (for example `goals/templates/Specification.md` mentioned in `docs/templates.md` comments), consider:

* either:

  * updating that specification to reference the new conventions; or
* if that file does not exist in this repo snapshot, creating a new `docs/strategy_iocm.md` or updating this `Strategy.md` into place.

The goal is that future contributors (human or LLM) can discover the I/O/C/M conventions by reading the docs, not just by reverse-engineering code.

---

## 8. Testing strategy

Remember the explicit constraint: **tests must be in separate files, not mixed with production code**.

### 8.1. New test modules to create

Create test modules under a top-level `tests/` directory, such as:

* `tests/test_template_interface.py` – tests for I/O/C/M interface extraction:

  * create a small in-repo template root in a temporary directory, with a simple template file using `I_document`, `C_style`, and `<O_main>...</O_main>`;
  * assert that `build_template_interface` returns the correct sets;
  * include tests where there are no `I_*` / `O_*` to ensure it handles empty cases gracefully.

* `tests/test_generation_capture_tag.py` – tests for `--capture-tag` behavior:

  * mock the streaming generator to yield a sequence of chunks with known text containing `<TAG>...</TAG>`;
  * test that `extract_between_tags` (or equivalent helper) returns the expected substring;
  * test behavior when tags are missing (raises `GenerationError` or returns empty with warning).

* `tests/test_cli_template_aliases.py` – tests for CLI alias behavior:

  * simulate calling `parse_args_for_new_cli(["template", "render", "prompts/summarize", "--document", "foo"])`;
  * assert that the resulting config includes the appropriate `user-instruction-template`;
  * test that `-t` / `--template` also map correctly.

If the project does not yet have a test harness (e.g., `pytest`), the agent should choose a mainstream one (pytest is typical) and:

* add minimal configuration if necessary;
* ensure tests run successfully in CI if CI configuration exists.

### 8.2. Test coverage goals

Aim for tests that cover:

* template interface extraction from Jinja AST (I/O/C/M classification);
* output tag scanning (`O_*` tags in template source);
* CLI integration logic (aliases and positional template name resolution);
* generation capture logic (`--capture-tag`, file writing, missing tag handling).

Do not mix tests into `src/gai/*.py`. All test code must live under `tests/`.

---

## 9. Implementation phases

### 9.1. Phase 1: internal helpers and interface extraction

Tasks:

1. Create a new module, for example `src/gai/template_interface.py`, containing:

   * `TemplateInterface` dataclass;
   * functions to build an interface given config and a logical name, using Jinja meta and tag scanning as described.

2. Add tests in `tests/test_template_interface.py` to validate behavior with small synthetic templates.

3. Ensure there are no circular imports; keep interface extraction independent of high-level CLI.

### 9.2. Phase 2: CLI commands for inspection

Tasks:

1. Extend `create_parser` in `src/gai/cli.py` to add `template inspect`:

   * `gai template inspect <logical_name>`;
   * hook into the `template` subparsers.

2. Implement `handle_template_inspect(config, parsed)` in `cli.py` (similar to other handlers):

   * call `build_template_interface` to get the interface;
   * print a human-readable summary.

3. Wire `handle_template_inspect` into `_handle_new_cli` in `src/gai/__main__.py`.

4. Add tests for `gai template inspect` in `tests/test_cli_template_inspect.py` (can stub interface responses).

### 9.3. Phase 3: CLI ergonomics for template selection

Tasks:

1. Introduce the `-t` / `--template` alias for user instruction template in `template render`.

2. Add the positional `template_name` argument to `template render`.

3. Implement logic in `_handle_new_cli` to translate aliases and positional args into `--conf-user-instruction-template` before calling `load_effective_config`.

4. Add tests simulating CLI parsing to ensure `template_name` and `--template` produce the expected effective config.

### 9.4. Phase 4: output capture in generate

Tasks:

1. Add `capture_tag` and `output_file` parameters to `generate()` in `src/gai/generation.py`:

   * either by extending the function signature;
   * or by passing an options dict or context object; choose the simpler but clear approach.

2. Implement `collect_output` and `extract_between_tags` helpers in `generation.py` (or a dedicated helper module) to:

   * collect full text from streaming generator;
   * extract text between `<TAG>` and `</TAG>`.

3. Integrate CLI options by extending the `generate` subparser in `cli.py` and wiring parsed options through `_handle_new_cli` to `generate`.

4. Add tests in `tests/test_generation_capture_tag.py` using mocked streaming responses.

### 9.5. Phase 5: documentation updates

Tasks:

1. Update `README.md` with:

   * new CLI usage examples (`--capture-tag`, `--output-file`, `-t` / positional template name);
   * a brief explanation of the I/O/C/M convention and how it helps.

2. Update `docs/templates.md` to include:

   * the I/O/C/M naming convention;
   * `gai template inspect` usage and sample output;
   * mentions of `--capture-tag` and output tagging patterns.

3. Ensure headings are in sentence case and prose is clear and not overly telegraphic.

4. Optionally, document this strategy or link to it from any existing specification index.

### 9.6. Phase 6: cleanup and refinement

Tasks:

1. Review code for consistency with the project’s error handling and logging style:

   * use existing exceptions (`TemplateError`, `GenerationError`) for new errors;
   * log helpful messages at appropriate levels.

2. Check that new features interact sensibly with existing ones:

   * `gai template render --part user` should still work when positional template name is used;
   * `gai generate --show-prompt` should be unaffected by `--capture-tag` (you can disable capture when `--show-prompt` is used).

3. Ensure that tests pass and that no tests reside in `src/`.

---

## 10. Summary for the LLM agent

When implementing this strategy in the `gai` repository, the LLM agent should:

* adopt the I/O/C/M naming convention internally for templates:

  * `I_*` for inputs;
  * `O_*` for output channel tags;
  * `C_*` for controls;
  * `M_*` for mechanisms.

* build a `TemplateInterface` from template code using Jinja `meta` and tag scanning, without requiring separate metadata files.

* add a `gai template inspect` subcommand to expose that interface to users.

* improve `gai template render` ergonomics with:

  * `-t` / `--template` aliases; and
  * an optional positional template name argument.

* extend `gai generate` to support `--capture-tag TAG` and `--output-file PATH` to replace manual `awk` extraction of `<output>` blocks.

* keep **tests strictly separate from code**, under a `tests/` directory, and create or extend tests for:

  * interface extraction;
  * CLI behavior for new flags and positional arguments;
  * capture-tag output extraction.

* update both `README.md` and `docs/templates.md` to reflect new conventions and CLI capabilities.

If the agent follows this strategy and keeps behavior well-tested, the result should be a more ergonomic, introspectable, and composable `gai` template system that aligns with the original design philosophy and greatly reduces the friction experienced by the user when working with templates and structured outputs.
