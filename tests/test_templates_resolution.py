"""Tests for template resolution logic."""

import pathlib

import jinja2
import pytest

from gai.exceptions import TemplateAmbiguityError, TemplateNotFoundError
from gai.template_catalog import TemplateRecord
from gai.templates import CatalogLoader, create_jinja_env_from_catalog, resolve_template_name


class TestResolveTemplateName:
    """Tests for the resolve_template_name function."""

    def test_resolve_simple_basename_match(self):
        """Test resolving a simple basename-only name."""
        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        result = resolve_template_name(catalog, "summary")
        assert result.logical_name_full == "summary"
        assert result.tier == "project"

    def test_resolve_path_specific_match(self):
        """Test resolving a path-specific name."""
        catalog = [
            TemplateRecord(
                logical_name_full="layout/base",
                relative_path=pathlib.Path("layout/base.j2"),
                absolute_path=pathlib.Path("/tmp/templates/layout/base.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        result = resolve_template_name(catalog, "layout/base")
        assert result.logical_name_full == "layout/base"

    def test_resolve_basename_matches_nested_path(self):
        """Test that basename-only match works for nested templates."""
        catalog = [
            TemplateRecord(
                logical_name_full="email/summary",
                relative_path=pathlib.Path("email/summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/email/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        # Basename "summary" should match "email/summary"
        result = resolve_template_name(catalog, "summary")
        assert result.logical_name_full == "email/summary"

    def test_resolve_explicit_extension(self):
        """Test resolving with an explicit extension."""
        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2.md"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2.md"),
                tier="project",
                root_index=0,
                extension=".j2.md",
            ),
        ]

        # With explicit extension, should resolve unambiguously
        result = resolve_template_name(catalog, "summary.j2")
        assert result.extension == ".j2"

        result = resolve_template_name(catalog, "summary.j2.md")
        assert result.extension == ".j2.md"

    def test_resolve_tier_precedence_project_wins(self):
        """Test that project tier takes precedence over user tier."""
        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/project/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/user/summary.j2"),
                tier="user",
                root_index=0,
                extension=".j2",
            ),
        ]

        result = resolve_template_name(catalog, "summary")
        assert result.tier == "project"
        assert "project" in str(result.absolute_path)

    def test_resolve_tier_precedence_user_when_project_absent(self):
        """Test that user tier is used when project tier has no match."""
        catalog = [
            TemplateRecord(
                logical_name_full="other",
                relative_path=pathlib.Path("other.j2"),
                absolute_path=pathlib.Path("/tmp/project/other.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/user/summary.j2"),
                tier="user",
                root_index=0,
                extension=".j2",
            ),
        ]

        result = resolve_template_name(catalog, "summary")
        assert result.tier == "user"

    def test_resolve_ambiguity_same_tier_different_extensions(self):
        """Test that multiple files with same name but different extensions in same tier cause ambiguity."""
        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2.md"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2.md"),
                tier="project",
                root_index=0,
                extension=".j2.md",
            ),
        ]

        # Without explicit extension, this is ambiguous
        with pytest.raises(TemplateAmbiguityError) as exc_info:
            resolve_template_name(catalog, "summary")

        assert exc_info.value.logical_name == "summary"
        assert exc_info.value.tier == "project"
        assert len(exc_info.value.candidates) == 2

    def test_resolve_ambiguity_same_tier_different_paths(self):
        """Test that multiple files with same basename in same tier cause ambiguity."""
        catalog = [
            TemplateRecord(
                logical_name_full="email/summary",
                relative_path=pathlib.Path("email/summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/email/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="report/summary",
                relative_path=pathlib.Path("report/summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/report/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
        ]

        # Basename "summary" matches both
        with pytest.raises(TemplateAmbiguityError) as exc_info:
            resolve_template_name(catalog, "summary")

        assert exc_info.value.logical_name == "summary"
        assert len(exc_info.value.candidates) == 2

    def test_resolve_ambiguity_resolved_by_path_specific(self):
        """Test that path-specific name resolves ambiguity."""
        catalog = [
            TemplateRecord(
                logical_name_full="email/summary",
                relative_path=pathlib.Path("email/summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/email/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="report/summary",
                relative_path=pathlib.Path("report/summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/report/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
        ]

        # Path-specific name should resolve unambiguously
        result = resolve_template_name(catalog, "email/summary")
        assert result.logical_name_full == "email/summary"

        result = resolve_template_name(catalog, "report/summary")
        assert result.logical_name_full == "report/summary"

    def test_resolve_not_found_empty_catalog(self):
        """Test that TemplateNotFoundError is raised for empty catalog."""
        catalog = []

        with pytest.raises(TemplateNotFoundError) as exc_info:
            resolve_template_name(catalog, "nonexistent")

        assert exc_info.value.logical_name == "nonexistent"

    def test_resolve_not_found_no_match(self):
        """Test that TemplateNotFoundError is raised when no templates match."""
        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        with pytest.raises(TemplateNotFoundError) as exc_info:
            resolve_template_name(catalog, "nonexistent")

        assert exc_info.value.logical_name == "nonexistent"

    def test_resolve_ambiguity_not_across_tiers(self):
        """Test that ambiguity only matters within a tier, not across tiers."""
        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/project/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/user/summary.j2"),
                tier="user",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/builtin/summary.j2"),
                tier="builtin",
                root_index=0,
                extension=".j2",
            ),
        ]

        # Should resolve to project tier without ambiguity error
        result = resolve_template_name(catalog, "summary")
        assert result.tier == "project"

    def test_resolve_user_tier_ambiguity_when_project_empty(self):
        """Test that ambiguity in user tier is fatal even if project tier exists but has no matches."""
        catalog = [
            TemplateRecord(
                logical_name_full="other",
                relative_path=pathlib.Path("other.j2"),
                absolute_path=pathlib.Path("/tmp/project/other.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/user/summary.j2"),
                tier="user",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2.md"),
                absolute_path=pathlib.Path("/tmp/user/summary.j2.md"),
                tier="user",
                root_index=0,
                extension=".j2.md",
            ),
        ]

        # Project tier has no "summary", user tier has ambiguity
        with pytest.raises(TemplateAmbiguityError) as exc_info:
            resolve_template_name(catalog, "summary")

        assert exc_info.value.tier == "user"


class TestCatalogLoader:
    """Tests for CatalogLoader integration with Jinja2."""

    def test_loader_get_source_simple(self, tmp_path):
        """Test that loader can retrieve template source."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        template_file = template_dir / "summary.j2"
        template_file.write_text("Hello {{ name }}!")

        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=template_file,
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        source, filename, uptodate = loader.get_source(env, "summary")

        assert source == "Hello {{ name }}!"
        assert str(template_file) in filename
        assert callable(uptodate)
        assert uptodate() is True

    def test_loader_get_source_not_found(self):
        """Test that loader raises TemplateNotFound for missing templates."""
        catalog = []
        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        with pytest.raises(jinja2.TemplateNotFound):
            loader.get_source(env, "nonexistent")

    def test_loader_get_source_ambiguous(self, tmp_path):
        """Test that loader raises TemplateNotFound with ambiguity message."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "summary.j2").write_text("Content 1")
        (template_dir / "summary.j2.md").write_text("Content 2")

        catalog = [
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=template_dir / "summary.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2.md"),
                absolute_path=template_dir / "summary.j2.md",
                tier="project",
                root_index=0,
                extension=".j2.md",
            ),
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        with pytest.raises(jinja2.TemplateNotFound) as exc_info:
            loader.get_source(env, "summary")

        # Should contain ambiguity information in the message
        assert "Ambiguous" in str(exc_info.value)

    def test_loader_render_template(self, tmp_path):
        """Test full template rendering through loader."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "greeting.j2").write_text("Hello {{ name }}!")

        catalog = [
            TemplateRecord(
                logical_name_full="greeting",
                relative_path=pathlib.Path("greeting.j2"),
                absolute_path=template_dir / "greeting.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        template = env.get_template("greeting")
        result = template.render(name="World")

        assert result == "Hello World!"

    def test_loader_template_extends(self, tmp_path):
        """Test that {% extends %} works with extensionless names."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()

        # Create base template
        (template_dir / "base.j2").write_text("BASE: {% block content %}default{% endblock %}")

        # Create child template that extends base
        (template_dir / "child.j2").write_text("{% extends 'base' %}{% block content %}child content{% endblock %}")

        catalog = [
            TemplateRecord(
                logical_name_full="base",
                relative_path=pathlib.Path("base.j2"),
                absolute_path=template_dir / "base.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="child",
                relative_path=pathlib.Path("child.j2"),
                absolute_path=template_dir / "child.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            ),
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        template = env.get_template("child")
        result = template.render()

        assert result == "BASE: child content"

    def test_loader_template_include(self, tmp_path):
        """Test that {% include %} works with extensionless names."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()

        (template_dir / "header.j2").write_text("HEADER")
        (template_dir / "main.j2").write_text("{% include 'header' %}\nMAIN")

        catalog = [
            TemplateRecord(
                logical_name_full="header",
                relative_path=pathlib.Path("header.j2"),
                absolute_path=template_dir / "header.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="main",
                relative_path=pathlib.Path("main.j2"),
                absolute_path=template_dir / "main.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            ),
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        template = env.get_template("main")
        result = template.render()

        assert "HEADER" in result
        assert "MAIN" in result

    def test_loader_nested_path_resolution(self, tmp_path):
        """Test that loader resolves nested paths correctly."""
        template_dir = tmp_path / "templates"
        layout_dir = template_dir / "layout"
        layout_dir.mkdir(parents=True)

        (layout_dir / "base.j2").write_text("Layout: {{ content }}")

        catalog = [
            TemplateRecord(
                logical_name_full="layout/base",
                relative_path=pathlib.Path("layout/base.j2"),
                absolute_path=layout_dir / "base.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        template = env.get_template("layout/base")
        result = template.render(content="test")

        assert result == "Layout: test"


class TestCreateJinjaEnvFromCatalog:
    """Tests for the create_jinja_env_from_catalog function."""

    def test_create_env_with_catalog(self, tmp_path):
        """Test creating a Jinja environment from catalog."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "test.j2").write_text("Test")

        catalog = [
            TemplateRecord(
                logical_name_full="test",
                relative_path=pathlib.Path("test.j2"),
                absolute_path=template_dir / "test.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        env = create_jinja_env_from_catalog(catalog)

        assert isinstance(env, jinja2.Environment)
        assert isinstance(env.loader, CatalogLoader)

        # Verify we can load templates
        template = env.get_template("test")
        assert template.render() == "Test"

    def test_env_uses_strict_undefined(self, tmp_path):
        """Test that the environment uses StrictUndefined."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "test.j2").write_text("{{ missing_var }}")

        catalog = [
            TemplateRecord(
                logical_name_full="test",
                relative_path=pathlib.Path("test.j2"),
                absolute_path=template_dir / "test.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        env = create_jinja_env_from_catalog(catalog)
        template = env.get_template("test")

        # Should raise UndefinedError for missing variable
        with pytest.raises(jinja2.UndefinedError):
            template.render()
