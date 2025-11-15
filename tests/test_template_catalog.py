"""Tests for template catalog and discovery."""

import pathlib

import pytest

from gai.template_catalog import (
    DEFAULT_TEMPLATE_EXTENSIONS,
    TIER_PRECEDENCE,
    TemplateCatalog,
    TemplateRecord,
    discover_templates,
)


class TestTemplateRecord:
    """Tests for TemplateRecord data structure."""

    def test_create_valid_record(self):
        """Test creating a valid template record."""
        record = TemplateRecord(
            logical_name_full="summary",
            relative_path=pathlib.Path("summary.j2"),
            absolute_path=pathlib.Path("/tmp/templates/summary.j2"),
            tier="project",
            root_index=0,
            extension=".j2",
        )
        assert record.logical_name_full == "summary"
        assert record.tier == "project"
        assert record.extension == ".j2"

    def test_invalid_tier(self):
        """Test that invalid tier raises ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2"),
                tier="invalid",  # type: ignore[arg-type]
                root_index=0,
                extension=".j2",
            )

    def test_invalid_extension(self):
        """Test that extension without dot raises ValueError."""
        with pytest.raises(ValueError, match="Extension must start with"):
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/summary.j2"),
                tier="project",
                root_index=0,
                extension="j2",  # Missing dot
            )


class TestDiscoverTemplates:
    """Tests for template discovery function."""

    def test_discover_empty_roots(self):
        """Test discovery with no roots configured."""
        records = discover_templates([], [], [])
        assert len(records) == 0

    def test_discover_nonexistent_roots(self):
        """Test discovery with nonexistent roots (should skip silently)."""
        nonexistent = pathlib.Path("/tmp/nonexistent_template_root_12345")
        records = discover_templates([nonexistent], [], [])
        assert len(records) == 0

    def test_discover_single_template(self, tmp_path):
        """Test discovery of a single template file."""
        # Create a template file
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "summary.j2").write_text("Template content")

        records = discover_templates([template_dir], [], [])

        assert len(records) == 1
        record = records[0]
        assert record.logical_name_full == "summary"
        assert record.relative_path == pathlib.Path("summary.j2")
        assert record.tier == "project"
        assert record.root_index == 0
        assert record.extension == ".j2"

    def test_discover_multiple_extensions(self, tmp_path):
        """Test discovery with different template extensions."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "file1.j2").write_text("Content")
        (template_dir / "file2.j2.md").write_text("Content")

        records = discover_templates([template_dir], [], [])

        assert len(records) == 2
        assert records[0].extension == ".j2"
        assert records[1].extension == ".j2.md"

    def test_discover_nested_directories(self, tmp_path):
        """Test discovery in nested directory structure."""
        template_dir = tmp_path / "templates"
        layout_dir = template_dir / "layout"
        layout_dir.mkdir(parents=True)

        (template_dir / "summary.j2").write_text("Content")
        (layout_dir / "base.j2").write_text("Content")

        records = discover_templates([template_dir], [], [])

        assert len(records) == 2
        # Should be sorted by relative path
        assert records[0].logical_name_full == "layout/base"
        assert records[1].logical_name_full == "summary"

    def test_discover_ignore_non_template_files(self, tmp_path):
        """Test that non-template files are ignored."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "template.j2").write_text("Content")
        (template_dir / "readme.txt").write_text("Not a template")
        (template_dir / "config.yaml").write_text("Not a template")

        records = discover_templates([template_dir], [], [])

        assert len(records) == 1
        assert records[0].logical_name_full == "template"

    def test_discover_multiple_roots_same_tier(self, tmp_path):
        """Test discovery with multiple roots in the same tier."""
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"
        root1.mkdir()
        root2.mkdir()

        (root1 / "file1.j2").write_text("Content")
        (root2 / "file2.j2").write_text("Content")

        records = discover_templates([root1, root2], [], [])

        assert len(records) == 2
        assert records[0].root_index == 0
        assert records[0].logical_name_full == "file1"
        assert records[1].root_index == 1
        assert records[1].logical_name_full == "file2"

    def test_discover_tier_precedence_ordering(self, tmp_path):
        """Test that templates are ordered by tier precedence."""
        project_dir = tmp_path / "project"
        user_dir = tmp_path / "user"
        builtin_dir = tmp_path / "builtin"

        for d in [project_dir, user_dir, builtin_dir]:
            d.mkdir()
            (d / "template.j2").write_text("Content")

        records = discover_templates([project_dir], [user_dir], [builtin_dir])

        assert len(records) == 3
        assert records[0].tier == "project"
        assert records[1].tier == "user"
        assert records[2].tier == "builtin"

    def test_discover_logical_name_with_subdirectories(self, tmp_path):
        """Test that logical names use forward slashes."""
        template_dir = tmp_path / "templates"
        nested = template_dir / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (nested / "deep.j2").write_text("Content")

        records = discover_templates([template_dir], [], [])

        assert len(records) == 1
        assert records[0].logical_name_full == "a/b/c/deep"
        # Ensure forward slashes even on Windows
        assert "/" in records[0].logical_name_full

    def test_discover_extension_stripping(self, tmp_path):
        """Test that extensions are properly stripped from logical names."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "file.j2").write_text("Content")
        (template_dir / "file2.j2.md").write_text("Content")

        records = discover_templates([template_dir], [], [])

        assert records[0].logical_name_full == "file"
        assert records[1].logical_name_full == "file2"
        # Ensure extensions don't appear in logical names
        assert ".j2" not in records[0].logical_name_full
        assert ".j2.md" not in records[1].logical_name_full

    def test_discover_custom_extensions(self, tmp_path):
        """Test discovery with custom allowed extensions."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "file.j2").write_text("Content")
        (template_dir / "file.txt").write_text("Content")

        # Only allow .txt extension
        records = discover_templates([template_dir], [], [], allowed_extensions=(".txt",))

        assert len(records) == 1
        assert records[0].extension == ".txt"

    def test_discover_ordering_within_tier(self, tmp_path):
        """Test that templates within a tier are ordered by root_index then path."""
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"
        root1.mkdir()
        root2.mkdir()

        # Create files in reverse alphabetical order in each root
        (root1 / "zebra.j2").write_text("Content")
        (root1 / "alpha.j2").write_text("Content")
        (root2 / "beta.j2").write_text("Content")

        records = discover_templates([root1, root2], [], [])

        assert len(records) == 3
        # Within root1, should be alphabetically sorted
        assert records[0].logical_name_full == "alpha"
        assert records[0].root_index == 0
        assert records[1].logical_name_full == "zebra"
        assert records[1].root_index == 0
        # Then root2
        assert records[2].logical_name_full == "beta"
        assert records[2].root_index == 1


class TestTemplateCatalog:
    """Tests for TemplateCatalog class."""

    def test_catalog_empty(self):
        """Test empty catalog."""
        catalog = TemplateCatalog([])
        assert len(catalog) == 0
        assert list(catalog) == []
        assert catalog.get_all_logical_names() == []

    def test_catalog_with_records(self, tmp_path):
        """Test catalog with multiple records."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "file1.j2").write_text("Content")
        (template_dir / "file2.j2").write_text("Content")

        records = discover_templates([template_dir], [], [])
        catalog = TemplateCatalog(records)

        assert len(catalog) == 2
        assert catalog.get_all_logical_names() == ["file1", "file2"]

    def test_catalog_filter_by_tier(self, tmp_path):
        """Test filtering catalog by tier."""
        project_dir = tmp_path / "project"
        user_dir = tmp_path / "user"
        project_dir.mkdir()
        user_dir.mkdir()

        (project_dir / "proj.j2").write_text("Content")
        (user_dir / "user.j2").write_text("Content")

        records = discover_templates([project_dir], [user_dir], [])
        catalog = TemplateCatalog(records)

        project_records = catalog.filter_by_tier("project")
        user_records = catalog.filter_by_tier("user")
        builtin_records = catalog.filter_by_tier("builtin")

        assert len(project_records) == 1
        assert len(user_records) == 1
        assert len(builtin_records) == 0
        assert project_records[0].logical_name_full == "proj"
        assert user_records[0].logical_name_full == "user"

    def test_catalog_iteration(self, tmp_path):
        """Test iterating over catalog."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "a.j2").write_text("Content")
        (template_dir / "b.j2").write_text("Content")

        records = discover_templates([template_dir], [], [])
        catalog = TemplateCatalog(records)

        names = [record.logical_name_full for record in catalog]
        assert names == ["a", "b"]


class TestTierPrecedence:
    """Tests for tier precedence constants."""

    def test_tier_precedence_order(self):
        """Test that tier precedence is correctly ordered."""
        assert TIER_PRECEDENCE["project"] < TIER_PRECEDENCE["user"]
        assert TIER_PRECEDENCE["user"] < TIER_PRECEDENCE["builtin"]

    def test_default_extensions(self):
        """Test default template extensions."""
        assert ".j2" in DEFAULT_TEMPLATE_EXTENSIONS
        assert ".j2.md" in DEFAULT_TEMPLATE_EXTENSIONS
