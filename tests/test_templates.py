"""Tests for template module."""

import pytest

from gai.exceptions import TemplateError
from gai.templates import render_template_string


def test_render_template_string_simple():
    """Test simple template rendering."""
    template = "Hello, {{ name }}!"
    variables = {"name": "World"}

    result = render_template_string(template, variables, "test")

    assert result == "Hello, World!"


def test_render_template_string_none():
    """Test None template handling."""
    result = render_template_string(None, {}, "test")

    assert result is None


def test_render_template_string_conditional():
    """Test conditional template rendering."""
    template = "{% if user is defined %}Hello, {{ user }}!{% else %}Hello, stranger!{% endif %}"

    result1 = render_template_string(template, {"user": "Alice"}, "test")
    assert result1 == "Hello, Alice!"

    result2 = render_template_string(template, {}, "test")
    assert result2 == "Hello, stranger!"


def test_render_template_string_complex():
    """Test complex template with multiple variables."""
    template = """<document>
{{ document }}
</document>

{% if input is defined %}
User Query: {{ input }}
{% endif %}"""

    variables = {
        "document": "This is a test document.",
        "input": "What is this about?",
    }

    result = render_template_string(template, variables, "test")

    assert "This is a test document." in result
    assert "User Query: What is this about?" in result


def test_render_template_string_undefined_variable():
    """Test that undefined variables raise TemplateError with StrictUndefined."""
    template = "Hello, {{ undefined_var }}!"
    variables = {}

    with pytest.raises(TemplateError):
        render_template_string(template, variables, "test")


def test_render_template_string_syntax_error():
    """Test that syntax errors raise TemplateError."""
    template = "Hello, {% if name %} {{ name {% endif %}!"
    variables = {"name": "World"}

    with pytest.raises(TemplateError):
        render_template_string(template, variables, "test")
