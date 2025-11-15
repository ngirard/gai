"""Tests for handling variables that contain Jinja template syntax.

This tests the behavior when template variables contain Jinja expressions like {{ var }}.
By default, these should be rendered as literal text (not recursively evaluated).
"""

import pathlib

import pytest

from gai.templates import render_user_instruction


@pytest.fixture
def simple_template(tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    """Create a simple template for testing variable rendering."""
    templates_root = tmp_path / ".gai" / "templates"
    templates_root.mkdir(parents=True)

    simple = templates_root / "simple.j2"
    simple.write_text(
        """Subject: {{ subject }}
Document: {{ doc }}""",
        encoding="utf-8",
    )

    return {
        "root": templates_root,
    }


def test_variable_with_jinja_syntax_rendered_literally(simple_template: dict[str, pathlib.Path]):
    """Test that variables containing Jinja syntax are rendered as literal text.

    This is the correct and secure behavior - variables should not be recursively
    evaluated as templates. If a variable contains '{{ var }}', it should appear
    in the output as '{{ var }}', not as the value of another variable.
    """
    config = {
        "project-template-paths": [str(simple_template["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "simple",
    }

    # subject contains Jinja syntax, which should be rendered literally
    template_vars = {
        "subject": "Identifying discrepancies between {{ doc }} and the codebase",
        "doc": "some/document.md",
    }

    result = render_user_instruction(config, template_vars)

    assert result is not None
    # The {{ doc }} in subject should appear literally, not be replaced with "some/document.md"
    assert "Subject: Identifying discrepancies between {{ doc }} and the codebase" in result
    assert "Document: some/document.md" in result


def test_variable_escaping_with_single_braces(simple_template: dict[str, pathlib.Path]):
    """Test that single braces in variables are rendered correctly."""
    config = {
        "project-template-paths": [str(simple_template["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "simple",
    }

    template_vars = {
        "subject": "Using {curly braces} in text",
        "doc": "test.md",
    }

    result = render_user_instruction(config, template_vars)

    assert result is not None
    assert "Using {curly braces} in text" in result


def test_preventing_template_injection(simple_template: dict[str, pathlib.Path]):
    """Test that template injection via variable values is prevented.

    This verifies that malicious or accidental template code in variable values
    cannot be executed. Variables are always treated as data, not code.
    """
    config = {
        "project-template-paths": [str(simple_template["root"])],
        "user-template-paths": [],
        "builtin-template-paths": [],
        "user-instruction-template": "simple",
    }

    # Try to inject template code via a variable
    template_vars = {
        "subject": "Attempt to inject: {% for i in range(10) %}X{% endfor %}",
        "doc": "{{ 'injection' }}",
    }

    result = render_user_instruction(config, template_vars)

    assert result is not None
    # The template code should appear literally, not be executed
    assert "{% for i in range(10) %}X{% endfor %}" in result
    assert "{{ 'injection' }}" in result
    # Should NOT see XXXXXXXXXX or the word "injection" by itself
    assert "XXXXXXXXXX" not in result
    # The literal string "{{ 'injection' }}" should be present
    assert "Document: {{ 'injection' }}" in result
