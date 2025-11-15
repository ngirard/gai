"""Additional edge case and robustness tests for template system.

This module contains additional tests for Phase 5 that cover edge cases
beyond the core specification, ensuring the system handles unusual inputs
and error conditions gracefully.
"""

import pathlib

import jinja2
import pytest

from gai.exceptions import TemplateAmbiguityError, TemplateNotFoundError
from gai.template_catalog import TemplateRecord, discover_templates
from gai.templates import CatalogLoader, resolve_template_name


class TestInvalidLogicalNames:
    """Tests for handling invalid or edge-case logical names."""

    def test_resolve_empty_logical_name(self):
        """Test that empty logical name raises TemplateNotFoundError."""
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
            resolve_template_name(catalog, "")

        assert exc_info.value.logical_name == ""

    def test_resolve_logical_name_with_leading_slash(self):
        """Test that logical name with leading slash is treated as path-specific."""
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

        # Leading slash should not match "summary"
        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, "/summary")

    def test_resolve_logical_name_with_trailing_slash(self):
        """Test that logical name with trailing slash doesn't match templates."""
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

        # Trailing slash should not match "summary"
        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, "summary/")

    def test_resolve_logical_name_with_consecutive_slashes(self):
        """Test that logical name with consecutive slashes doesn't match."""
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

        # Double slash should not match
        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, "layout//base")

    def test_resolve_logical_name_with_dot_segments(self):
        """Test that logical names with . or .. segments don't match."""
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

        # Path traversal attempts should not match
        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, "./layout/base")

        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, "layout/../layout/base")

    def test_resolve_logical_name_with_whitespace(self):
        """Test that logical names with whitespace are treated literally."""
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

        # Leading/trailing whitespace should not match
        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, " summary")

        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, "summary ")

    def test_resolve_logical_name_case_sensitive(self):
        """Test that logical name resolution is case-sensitive."""
        catalog = [
            TemplateRecord(
                logical_name_full="Summary",
                relative_path=pathlib.Path("Summary.j2"),
                absolute_path=pathlib.Path("/tmp/templates/Summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        # Case mismatch should not match
        with pytest.raises(TemplateNotFoundError):
            resolve_template_name(catalog, "summary")

        # Exact case should match
        result = resolve_template_name(catalog, "Summary")
        assert result.logical_name_full == "Summary"


class TestPathHandlingEdgeCases:
    """Tests for edge cases in path handling and normalization."""

    def test_discover_templates_with_dot_files(self, tmp_path):
        """Test that hidden files (starting with .) are discovered if they have template extensions."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / ".hidden.j2").write_text("Hidden template")
        (template_dir / "visible.j2").write_text("Visible template")

        records = discover_templates([template_dir], [], [])

        # Both should be discovered
        assert len(records) == 2
        logical_names = [r.logical_name_full for r in records]
        assert ".hidden" in logical_names
        assert "visible" in logical_names

    def test_discover_deeply_nested_directories(self, tmp_path):
        """Test discovery in very deeply nested directory structures."""
        template_dir = tmp_path / "templates"
        deep_dir = template_dir / "a" / "b" / "c" / "d" / "e" / "f" / "g"
        deep_dir.mkdir(parents=True)
        (deep_dir / "deep.j2").write_text("Deep template")

        records = discover_templates([template_dir], [], [])

        assert len(records) == 1
        assert records[0].logical_name_full == "a/b/c/d/e/f/g/deep"

    def test_discover_templates_handles_symlinks(self, tmp_path):
        """Test that symlinks are handled gracefully (may or may not be followed)."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        actual_dir = tmp_path / "actual"
        actual_dir.mkdir()
        (actual_dir / "template.j2").write_text("Content")

        # Create symlink to actual directory
        link_dir = template_dir / "linked"
        try:
            link_dir.symlink_to(actual_dir)
            records = discover_templates([template_dir], [], [])

            # Symlink behavior may vary by system; just ensure no crash
            # On systems that follow symlinks, we should find the template
            logical_names = [r.logical_name_full for r in records]

            # The test passes if either:
            # 1. Symlinks are followed and we find the template
            # 2. Symlinks are not followed and we find nothing
            # Both are acceptable behaviors
            if len(records) > 0:
                assert "linked/template" in logical_names
        except (OSError, PermissionError):
            # Symlinks may not be supported or allowed on all systems
            pytest.skip("Symlinks not supported or not allowed on this system")


class TestTemplateFileEdgeCases:
    """Tests for edge cases related to template file contents and handling."""

    def test_empty_template_file(self, tmp_path):
        """Test that empty template files are handled correctly."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "empty.j2").write_text("")

        catalog = [
            TemplateRecord(
                logical_name_full="empty",
                relative_path=pathlib.Path("empty.j2"),
                absolute_path=template_dir / "empty.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        template = env.get_template("empty")
        result = template.render()
        assert result == ""

    def test_template_with_unicode_content(self, tmp_path):
        """Test that templates with Unicode content are handled correctly."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        unicode_content = "Hello {{ name }}! 你好 🌟 مرحبا"
        (template_dir / "unicode.j2").write_text(unicode_content, encoding="utf-8")

        catalog = [
            TemplateRecord(
                logical_name_full="unicode",
                relative_path=pathlib.Path("unicode.j2"),
                absolute_path=template_dir / "unicode.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        template = env.get_template("unicode")
        result = template.render(name="World")
        assert "Hello World!" in result
        assert "你好" in result
        assert "🌟" in result
        assert "مرحبا" in result

    def test_template_with_very_long_lines(self, tmp_path):
        """Test that templates with very long lines are handled correctly."""
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        long_line = "a" * 10000
        (template_dir / "long.j2").write_text(long_line)

        catalog = [
            TemplateRecord(
                logical_name_full="long",
                relative_path=pathlib.Path("long.j2"),
                absolute_path=template_dir / "long.j2",
                tier="project",
                root_index=0,
                extension=".j2",
            )
        ]

        loader = CatalogLoader(catalog)
        env = jinja2.Environment(loader=loader)

        template = env.get_template("long")
        result = template.render()
        assert len(result) == 10000


class TestComplexResolutionScenarios:
    """Tests for complex multi-tier, multi-root resolution scenarios."""

    def test_resolution_with_three_tiers_same_name(self):
        """Test resolution when same template exists in all three tiers."""
        catalog = [
            TemplateRecord(
                logical_name_full="common",
                relative_path=pathlib.Path("common.j2"),
                absolute_path=pathlib.Path("/tmp/project/common.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="common",
                relative_path=pathlib.Path("common.j2"),
                absolute_path=pathlib.Path("/tmp/user/common.j2"),
                tier="user",
                root_index=0,
                extension=".j2",
            ),
            TemplateRecord(
                logical_name_full="common",
                relative_path=pathlib.Path("common.j2"),
                absolute_path=pathlib.Path("/tmp/builtin/common.j2"),
                tier="builtin",
                root_index=0,
                extension=".j2",
            ),
        ]

        result = resolve_template_name(catalog, "common")
        assert result.tier == "project"
        assert "project" in str(result.absolute_path)

    def test_resolution_with_multiple_roots_per_tier(self):
        """Test resolution when each tier has multiple roots."""
        catalog = [
            # Project tier, root 0
            TemplateRecord(
                logical_name_full="proj1",
                relative_path=pathlib.Path("proj1.j2"),
                absolute_path=pathlib.Path("/tmp/project1/proj1.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            # Project tier, root 1
            TemplateRecord(
                logical_name_full="proj2",
                relative_path=pathlib.Path("proj2.j2"),
                absolute_path=pathlib.Path("/tmp/project2/proj2.j2"),
                tier="project",
                root_index=1,
                extension=".j2",
            ),
            # User tier, root 0
            TemplateRecord(
                logical_name_full="user1",
                relative_path=pathlib.Path("user1.j2"),
                absolute_path=pathlib.Path("/tmp/user1/user1.j2"),
                tier="user",
                root_index=0,
                extension=".j2",
            ),
        ]

        # Each should resolve correctly
        assert resolve_template_name(catalog, "proj1").root_index == 0
        assert resolve_template_name(catalog, "proj2").root_index == 1
        assert resolve_template_name(catalog, "user1").tier == "user"

    def test_ambiguity_across_multiple_roots_same_tier(self):
        """Test that ambiguity is detected across multiple roots in the same tier."""
        catalog = [
            # Project tier, root 0
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/project1/summary.j2"),
                tier="project",
                root_index=0,
                extension=".j2",
            ),
            # Project tier, root 1
            TemplateRecord(
                logical_name_full="summary",
                relative_path=pathlib.Path("summary.j2"),
                absolute_path=pathlib.Path("/tmp/project2/summary.j2"),
                tier="project",
                root_index=1,
                extension=".j2",
            ),
        ]

        # Should raise ambiguity because both are in project tier
        with pytest.raises(TemplateAmbiguityError) as exc_info:
            resolve_template_name(catalog, "summary")

        assert exc_info.value.tier == "project"
        assert len(exc_info.value.candidates) == 2


class TestErrorMessageQuality:
    """Tests that error messages are clear and actionable."""

    def test_not_found_error_includes_searched_name(self):
        """Test that TemplateNotFoundError includes the searched name."""
        catalog = []

        with pytest.raises(TemplateNotFoundError) as exc_info:
            resolve_template_name(catalog, "nonexistent/template")

        assert "nonexistent/template" in str(exc_info.value)
        assert exc_info.value.logical_name == "nonexistent/template"

    def test_ambiguity_error_includes_candidates(self):
        """Test that TemplateAmbiguityError includes candidate information."""
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

        with pytest.raises(TemplateAmbiguityError) as exc_info:
            resolve_template_name(catalog, "summary")

        error = exc_info.value
        assert error.logical_name == "summary"
        assert error.tier == "project"
        assert len(error.candidates) == 2
        # Candidates are tuples of (path, extension)
        assert all(isinstance(c, tuple) and len(c) == 2 for c in error.candidates)
        # Check that both extensions are represented
        extensions = [c[1] for c in error.candidates]
        assert ".j2" in extensions
        assert ".j2.md" in extensions

    def test_loader_error_message_for_ambiguity(self, tmp_path):
        """Test that CatalogLoader provides clear error message for ambiguity."""
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

        # Error message should mention ambiguity
        assert "Ambiguous" in str(exc_info.value) or "ambiguous" in str(exc_info.value)


class TestCatalogRobustness:
    """Tests for catalog construction robustness."""

    def test_discover_with_all_empty_tiers(self):
        """Test discovery when all tier lists are empty."""
        records = discover_templates([], [], [])
        assert len(records) == 0

    def test_discover_with_mixed_existing_nonexisting_roots(self, tmp_path):
        """Test discovery with mix of existing and non-existing roots."""
        existing = tmp_path / "existing"
        existing.mkdir()
        (existing / "template.j2").write_text("Content")

        nonexisting = tmp_path / "nonexisting"

        records = discover_templates([existing, nonexisting], [], [])

        # Should discover from existing, skip nonexisting
        assert len(records) == 1
        assert records[0].logical_name_full == "template"

    def test_discover_preserves_order_across_tiers(self, tmp_path):
        """Test that catalog order respects tier precedence."""
        project_dir = tmp_path / "project"
        user_dir = tmp_path / "user"
        builtin_dir = tmp_path / "builtin"

        for d in [project_dir, user_dir, builtin_dir]:
            d.mkdir()
            (d / "a.j2").write_text("Content")
            (d / "z.j2").write_text("Content")

        records = discover_templates([project_dir], [user_dir], [builtin_dir])

        # Should have 6 records total
        assert len(records) == 6

        # First two should be from project tier
        assert records[0].tier == "project"
        assert records[1].tier == "project"

        # Next two from user tier
        assert records[2].tier == "user"
        assert records[3].tier == "user"

        # Last two from builtin tier
        assert records[4].tier == "builtin"
        assert records[5].tier == "builtin"
