"""Tests for template recursion and nested template resolution.

This module tests that named templates can recursively include, extend, and import
each other, and that variables are properly expanded across all nesting levels.
"""

import pathlib

import pytest

from gai.exceptions import TemplateError, TemplateNotFoundError
from gai.templates import render_system_instruction, render_user_instruction


@pytest.fixture
def template_fixtures(tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    """Create a temporary template directory structure for testing recursion.

    Creates the following structure:
        <tmp>/.gai/templates/
          layout/
            base_conversation.j2
          partials/
            output_format.j2
            greeting.j2
          prompts/
            nested_include.j2
            nested_extends.j2
            double_nested.j2
    """
    templates_root = tmp_path / ".gai" / "templates"
    templates_root.mkdir(parents=True)

    # Create layout directory and base template
    layout_dir = templates_root / "layout"
    layout_dir.mkdir()

    base_conversation = layout_dir / "base_conversation.j2"
    base_conversation.write_text(
        """You are {{ role }}.

{% block task %}
[base task]
{% endblock %}

{% block signature %}
-- End of instruction --
{% endblock %}""",
        encoding="utf-8",
    )

    # Create partials directory
    partials_dir = templates_root / "partials"
    partials_dir.mkdir()

    output_format = partials_dir / "output_format.j2"
    output_format.write_text(
        """Output format:
- variable: {{ important_var }}
- context: {{ context_var }}""",
        encoding="utf-8",
    )

    greeting = partials_dir / "greeting.j2"
    greeting.write_text(
        """Hello {{ username }}!""",
        encoding="utf-8",
    )

    # Create prompts directory
    prompts_dir = templates_root / "prompts"
    prompts_dir.mkdir()

    # Template that extends base and includes a partial
    nested_include = prompts_dir / "nested_include.j2"
    nested_include.write_text(
        """{% extends "layout/base_conversation" %}

{% block task %}
This is a nested task for {{ subject }}.

{% include "partials/output_format" %}
{% endblock %}""",
        encoding="utf-8",
    )

    # Template that extends base with different blocks
    nested_extends = prompts_dir / "nested_extends.j2"
    nested_extends.write_text(
        """{% extends "layout/base_conversation" %}

{% block task %}
Working on: {{ task_name }}
{% endblock %}

{% block signature %}
Signed by {{ author }}
{% endblock %}""",
        encoding="utf-8",
    )

    # Template that includes multiple partials
    double_nested = prompts_dir / "double_nested.j2"
    double_nested.write_text(
        """{% extends "layout/base_conversation" %}

{% block task %}
{% include "partials/greeting" %}

Task details for {{ subject }}:
{% include "partials/output_format" %}
{% endblock %}""",
        encoding="utf-8",
    )

    return {
        "root": templates_root,
        "layout_dir": layout_dir,
        "partials_dir": partials_dir,
        "prompts_dir": prompts_dir,
    }


def test_simple_include_recursion(template_fixtures: dict[str, pathlib.Path]):
    """Test that a template can include another template and expand variables."""
    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "prompts/nested_include",
    }

    template_vars = {
        "role": "a test assistant",
        "subject": "recursive templates",
        "important_var": "SHOULD_BE_EXPANDED",
        "context_var": "CONTEXT_VALUE",
    }

    result = render_user_instruction(config, template_vars)

    # Verify that all variables were expanded
    assert result is not None
    assert "a test assistant" in result
    assert "recursive templates" in result
    assert "SHOULD_BE_EXPANDED" in result
    assert "CONTEXT_VALUE" in result
    assert "Output format:" in result
    assert "-- End of instruction --" in result


def test_extends_with_blocks(template_fixtures: dict[str, pathlib.Path]):
    """Test that template extension works with block overrides."""
    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "system-instruction-template": "prompts/nested_extends",
    }

    template_vars = {
        "role": "code reviewer",
        "task_name": "review pull request",
        "author": "Test Bot",
    }

    result = render_system_instruction(config, template_vars)

    assert result is not None
    assert "code reviewer" in result
    assert "review pull request" in result
    assert "Signed by Test Bot" in result
    assert "[base task]" not in result  # Should be overridden


def test_multiple_includes(template_fixtures: dict[str, pathlib.Path]):
    """Test that a template can include multiple partials."""
    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "prompts/double_nested",
    }

    template_vars = {
        "role": "assistant",
        "subject": "multi-include test",
        "username": "TestUser",
        "important_var": "VAR1",
        "context_var": "VAR2",
    }

    result = render_user_instruction(config, template_vars)

    assert result is not None
    assert "assistant" in result
    assert "Hello TestUser!" in result
    assert "multi-include test" in result
    assert "VAR1" in result
    assert "VAR2" in result


def test_missing_variable_in_nested_template(template_fixtures: dict[str, pathlib.Path]):
    """Test that missing variables in nested templates raise proper errors."""
    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "prompts/nested_include",
    }

    # Missing 'important_var' which is used in the included partial
    template_vars = {
        "role": "assistant",
        "subject": "test",
        "context_var": "value",
        # important_var is missing  # noqa: ERA001
    }

    with pytest.raises(TemplateError) as exc_info:
        render_user_instruction(config, template_vars)

    # The error should mention the missing variable
    assert "important_var" in str(exc_info.value)


def test_nonexistent_included_template(template_fixtures: dict[str, pathlib.Path]):
    """Test that referencing a nonexistent template in an include raises an error."""
    # Create a template that tries to include a nonexistent template
    prompts_dir = template_fixtures["prompts_dir"]
    bad_template = prompts_dir / "bad_include.j2"
    bad_template.write_text(
        """{% extends "layout/base_conversation" %}

{% block task %}
{% include "partials/nonexistent" %}
{% endblock %}""",
        encoding="utf-8",
    )

    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "prompts/bad_include",
    }

    template_vars = {
        "role": "assistant",
    }

    # The rendering should fail due to the nonexistent include
    # It could fail at different points depending on when Jinja tries to load the nested template
    with pytest.raises((TemplateError, TemplateNotFoundError)):
        render_user_instruction(config, template_vars)


def test_system_instruction_with_recursion(template_fixtures: dict[str, pathlib.Path]):
    """Test that system-instruction-template supports recursion."""
    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "system-instruction-template": "prompts/nested_include",
    }

    template_vars = {
        "role": "system assistant",
        "subject": "system level test",
        "important_var": "SYS_VAR",
        "context_var": "SYS_CONTEXT",
    }

    result = render_system_instruction(config, template_vars)

    assert result is not None
    assert "system assistant" in result
    assert "system level test" in result
    assert "SYS_VAR" in result
    assert "SYS_CONTEXT" in result


def test_extensionless_template_names(template_fixtures: dict[str, pathlib.Path]):
    """Test that extensionless logical names work for nested includes."""
    # This test verifies that {% include "partials/output_format" %} works
    # without needing to specify .j2 extension
    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "prompts/nested_include",
    }

    template_vars = {
        "role": "assistant",
        "subject": "extensionless test",
        "important_var": "VALUE",
        "context_var": "CTX",
    }

    # This should succeed without errors
    result = render_user_instruction(config, template_vars)
    assert result is not None
    assert "VALUE" in result


def test_template_with_explicit_extension(template_fixtures: dict[str, pathlib.Path]):
    """Test that templates can be referenced with explicit .j2 extension."""
    # Create a template that uses explicit extension in include
    prompts_dir = template_fixtures["prompts_dir"]
    explicit_ext = prompts_dir / "explicit_extension.j2"
    explicit_ext.write_text(
        """{% extends "layout/base_conversation.j2" %}

{% block task %}
Testing explicit extension for {{ subject }}.
{% include "partials/output_format.j2" %}
{% endblock %}""",
        encoding="utf-8",
    )

    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "prompts/explicit_extension",
    }

    template_vars = {
        "role": "assistant",
        "subject": "explicit ext test",
        "important_var": "EXT_VAR",
        "context_var": "EXT_CTX",
    }

    result = render_user_instruction(config, template_vars)
    assert result is not None
    assert "explicit ext test" in result
    assert "EXT_VAR" in result


def test_literal_template_without_recursion():
    """Test that literal templates (user-instruction) do not support catalog-based includes.

    This documents the current expected behavior: literal instruction strings
    use a simple FileSystemLoader and do not have access to the template catalog.
    """
    # Using a literal template that tries to include a named template
    config = {
        "project-template-paths": [],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction": """Literal template for {{ subject }}.
{% include "partials/output_format" %}""",
    }

    template_vars = {
        "subject": "literal test",
        "important_var": "LITERAL_VAR",
        "context_var": "LITERAL_CTX",
    }

    # This should fail because literal templates don't use the catalog
    with pytest.raises(TemplateError):
        render_user_instruction(config, template_vars)


def test_three_level_nesting(template_fixtures: dict[str, pathlib.Path]):
    """Test three levels of template nesting: extends -> includes -> includes."""
    # Create a nested partial that itself includes another partial
    partials_dir = template_fixtures["partials_dir"]
    meta_partial = partials_dir / "meta_partial.j2"
    meta_partial.write_text(
        """Meta section:
{% include "partials/greeting" %}
Value: {{ meta_value }}""",
        encoding="utf-8",
    )

    prompts_dir = template_fixtures["prompts_dir"]
    three_level = prompts_dir / "three_level.j2"
    three_level.write_text(
        """{% extends "layout/base_conversation" %}

{% block task %}
Task: {{ task_desc }}
{% include "partials/meta_partial" %}
{% endblock %}""",
        encoding="utf-8",
    )

    config = {
        "project-template-paths": [str(template_fixtures["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "prompts/three_level",
    }

    template_vars = {
        "role": "deep nesting assistant",
        "task_desc": "test three levels",
        "username": "NestUser",
        "meta_value": "DEEP_VALUE",
    }

    result = render_user_instruction(config, template_vars)

    assert result is not None
    assert "deep nesting assistant" in result
    assert "test three levels" in result
    assert "Hello NestUser!" in result
    assert "DEEP_VALUE" in result
