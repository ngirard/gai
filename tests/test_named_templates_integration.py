"""Integration tests for named template rendering.

Tests the complete flow of named template resolution and rendering,
including precedence rules between named templates and literal templates.
"""

import pathlib
from typing import Any

import pytest

from gai.generation import prepare_generate_content_config_dict, prepare_prompt_contents
from gai.templates import render_system_instruction, render_user_instruction


@pytest.fixture
def temp_template_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a temporary directory for template files."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    return template_dir


@pytest.fixture
def config_with_template_roots(temp_template_dir: pathlib.Path) -> dict[str, Any]:
    """Create a config with template roots pointing to temp directory."""
    return {
        "project-template-paths": [str(temp_template_dir)],
        "user-template-paths": None,
        "builtin-template-paths": None,
        "system-instruction": "Literal system instruction",
        "user-instruction": "Literal user instruction",
        "system-instruction-template": None,
        "user-instruction-template": None,
        "temperature": 0.1,
        "response-mime-type": "text/plain",
        "max-output-tokens": None,
        "model": "gemini-flash-latest",
    }


class TestNamedTemplateRendering:
    """Tests for named template rendering with the new helper functions."""

    def test_render_user_instruction_with_literal_template(self, config_with_template_roots: dict[str, Any]):
        """Test that literal user instruction works (backward compatibility)."""
        config = config_with_template_roots
        config["user-instruction"] = "Hello {{ name }}!"
        template_vars = {"name": "World"}

        result = render_user_instruction(config, template_vars)
        assert result == "Hello World!"

    def test_render_system_instruction_with_literal_template(self, config_with_template_roots: dict[str, Any]):
        """Test that literal system instruction works (backward compatibility)."""
        config = config_with_template_roots
        config["system-instruction"] = "System: {{ role }}"
        template_vars = {"role": "assistant"}

        result = render_system_instruction(config, template_vars)
        assert result == "System: assistant"

    def test_render_user_instruction_with_named_template(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test that named user instruction template is resolved and rendered."""
        # Create a template file
        template_file = temp_template_dir / "user_greeting.j2"
        template_file.write_text("Hello {{ name }} from template!")

        # Configure to use named template
        config = config_with_template_roots
        config["user-instruction"] = "This should be ignored"
        config["user-instruction-template"] = "user_greeting"
        template_vars = {"name": "Alice"}

        result = render_user_instruction(config, template_vars)
        assert result == "Hello Alice from template!"

    def test_render_system_instruction_with_named_template(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test that named system instruction template is resolved and rendered."""
        # Create a template file
        template_file = temp_template_dir / "system_role.j2"
        template_file.write_text("System role: {{ role }}")

        # Configure to use named template
        config = config_with_template_roots
        config["system-instruction"] = "This should be ignored"
        config["system-instruction-template"] = "system_role"
        template_vars = {"role": "expert"}

        result = render_system_instruction(config, template_vars)
        assert result == "System role: expert"

    def test_named_template_precedence_over_literal(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test that named template takes precedence over literal template."""
        # Create template files
        (temp_template_dir / "user_msg.j2").write_text("Named: {{ msg }}")
        (temp_template_dir / "system_msg.j2").write_text("Named System: {{ msg }}")

        config = config_with_template_roots
        config["user-instruction"] = "Literal: {{ msg }}"
        config["user-instruction-template"] = "user_msg"
        config["system-instruction"] = "Literal System: {{ msg }}"
        config["system-instruction-template"] = "system_msg"
        template_vars = {"msg": "test"}

        user_result = render_user_instruction(config, template_vars)
        system_result = render_system_instruction(config, template_vars)

        assert user_result == "Named: test"
        assert system_result == "Named System: test"

    def test_named_template_with_nested_path(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test that named templates can be resolved from nested directories."""
        # Create nested directory structure
        nested_dir = temp_template_dir / "prompts" / "user"
        nested_dir.mkdir(parents=True)
        template_file = nested_dir / "greeting.j2"
        template_file.write_text("Nested greeting: {{ name }}")

        config = config_with_template_roots
        config["user-instruction-template"] = "prompts/user/greeting"
        template_vars = {"name": "Bob"}

        result = render_user_instruction(config, template_vars)
        assert result == "Nested greeting: Bob"

    def test_named_template_with_extends(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test that named templates can use {% extends %} for composition."""
        # Create base template
        base_template = temp_template_dir / "base.j2"
        base_template.write_text("Base: {% block content %}default{% endblock %}")

        # Create child template
        child_template = temp_template_dir / "child.j2"
        child_template.write_text('{% extends "base" %}{% block content %}{{ msg }}{% endblock %}')

        config = config_with_template_roots
        config["user-instruction-template"] = "child"
        template_vars = {"msg": "extended content"}

        result = render_user_instruction(config, template_vars)
        assert result == "Base: extended content"

    def test_named_template_with_include(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test that named templates can use {% include %} for composition."""
        # Create partial template
        partial = temp_template_dir / "header.j2"
        partial.write_text("Header: {{ title }}")

        # Create main template
        main_template = temp_template_dir / "main.j2"
        main_template.write_text('{% include "header" %}\nBody: {{ content }}')

        config = config_with_template_roots
        config["user-instruction-template"] = "main"
        template_vars = {"title": "Welcome", "content": "Hello"}

        result = render_user_instruction(config, template_vars)
        # Note: Jinja2 with trim_blocks=True and lstrip_blocks=True trims the newline
        assert result == "Header: WelcomeBody: Hello"

    def test_named_template_returns_none_when_not_configured(self, config_with_template_roots: dict[str, Any]):
        """Test that None is returned when no instruction is configured."""
        config = config_with_template_roots
        config["user-instruction"] = None
        config["user-instruction-template"] = None
        config["system-instruction"] = None
        config["system-instruction-template"] = None

        user_result = render_user_instruction(config, {})
        system_result = render_system_instruction(config, {})

        assert user_result is None
        assert system_result is None


class TestGenerationIntegration:
    """Tests for integration with generation.py functions."""

    def test_prepare_prompt_contents_with_literal(self, config_with_template_roots: dict[str, Any]):
        """Test prepare_prompt_contents with literal template."""
        config = config_with_template_roots
        config["user-instruction"] = "User message: {{ msg }}"
        template_vars = {"msg": "test"}

        contents = prepare_prompt_contents(config, template_vars)

        assert len(contents) == 1
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "User message: test"

    def test_prepare_prompt_contents_with_named_template(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test prepare_prompt_contents with named template."""
        # Create template
        (temp_template_dir / "user_prompt.j2").write_text("Named user: {{ msg }}")

        config = config_with_template_roots
        config["user-instruction-template"] = "user_prompt"
        template_vars = {"msg": "hello"}

        contents = prepare_prompt_contents(config, template_vars)

        assert len(contents) == 1
        assert contents[0].parts[0].text == "Named user: hello"

    def test_prepare_generate_content_config_dict_with_literal(self, config_with_template_roots: dict[str, Any]):
        """Test prepare_generate_content_config_dict with literal template."""
        config = config_with_template_roots
        config["system-instruction"] = "System: {{ role }}"
        template_vars = {"role": "assistant"}

        result = prepare_generate_content_config_dict(config, template_vars)

        assert result["system_instruction"] == "System: assistant"
        assert result["temperature"] == 0.1
        assert result["response_mime_type"] == "text/plain"

    def test_prepare_generate_content_config_dict_with_named_template(
        self, config_with_template_roots: dict[str, Any], temp_template_dir: pathlib.Path
    ):
        """Test prepare_generate_content_config_dict with named template."""
        # Create template
        (temp_template_dir / "system_prompt.j2").write_text("Named system: {{ role }}")

        config = config_with_template_roots
        config["system-instruction-template"] = "system_prompt"
        template_vars = {"role": "expert"}

        result = prepare_generate_content_config_dict(config, template_vars)

        assert result["system_instruction"] == "Named system: expert"

    def test_prepare_generate_content_config_dict_no_system_instruction(
        self, config_with_template_roots: dict[str, Any]
    ):
        """Test that system_instruction is omitted when not configured."""
        config = config_with_template_roots
        config["system-instruction"] = None
        config["system-instruction-template"] = None

        result = prepare_generate_content_config_dict(config, {})

        assert "system_instruction" not in result
        assert result["temperature"] == 0.1
