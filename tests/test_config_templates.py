"""Tests for template-related configuration functionality."""

import pathlib

from gai.config import CONFIG_TYPES, DEFAULT_CONFIG, get_template_roots


class TestTemplateConfigKeys:
    """Tests for template configuration keys and types."""

    def test_template_paths_in_default_config(self):
        """Test that template path keys exist in default config."""
        assert "project-template-paths" in DEFAULT_CONFIG
        assert "user-template-paths" in DEFAULT_CONFIG
        assert "builtin-template-paths" in DEFAULT_CONFIG

    def test_template_instruction_keys_in_default_config(self):
        """Test that template instruction keys exist in default config."""
        assert "system-instruction-template" in DEFAULT_CONFIG
        assert "user-instruction-template" in DEFAULT_CONFIG

    def test_template_config_types(self):
        """Test that template config types are correct."""
        assert CONFIG_TYPES["project-template-paths"] == list
        assert CONFIG_TYPES["user-template-paths"] == list
        assert CONFIG_TYPES["builtin-template-paths"] == list
        assert CONFIG_TYPES["system-instruction-template"] == str
        assert CONFIG_TYPES["user-instruction-template"] == str

    def test_default_template_values_are_none(self):
        """Test that template defaults are None."""
        assert DEFAULT_CONFIG["project-template-paths"] is None
        assert DEFAULT_CONFIG["user-template-paths"] is None
        assert DEFAULT_CONFIG["builtin-template-paths"] is None
        assert DEFAULT_CONFIG["system-instruction-template"] is None
        assert DEFAULT_CONFIG["user-instruction-template"] is None


class TestGetTemplateRoots:
    """Tests for get_template_roots function."""

    def test_empty_config(self):
        """Test with no template paths configured."""
        config = {}
        roots = get_template_roots(config)

        assert roots["project"] == []
        assert roots["user"] == []
        assert roots["builtin"] == []

    def test_config_with_none_values(self):
        """Test with None template paths."""
        config = {
            "project-template-paths": None,
            "user-template-paths": None,
            "builtin-template-paths": None,
        }
        roots = get_template_roots(config)

        assert roots["project"] == []
        assert roots["user"] == []
        assert roots["builtin"] == []

    def test_absolute_paths(self):
        """Test resolution of absolute paths."""
        config = {
            "project-template-paths": ["/tmp/project"],
            "user-template-paths": ["/tmp/user"],
            "builtin-template-paths": ["/tmp/builtin"],
        }
        roots = get_template_roots(config)

        assert len(roots["project"]) == 1
        assert roots["project"][0] == pathlib.Path("/tmp/project")
        assert len(roots["user"]) == 1
        assert roots["user"][0] == pathlib.Path("/tmp/user")
        assert len(roots["builtin"]) == 1
        assert roots["builtin"][0] == pathlib.Path("/tmp/builtin")

    def test_tilde_expansion(self):
        """Test that tilde is expanded to home directory."""
        config = {
            "user-template-paths": ["~/.config/gai/templates"],
        }
        roots = get_template_roots(config)

        assert len(roots["user"]) == 1
        # Should not contain tilde
        assert "~" not in str(roots["user"][0])
        # Should be an absolute path
        assert roots["user"][0].is_absolute()

    def test_relative_project_paths(self):
        """Test that relative project paths are resolved against repo/cwd."""
        config = {
            "project-template-paths": [".gai/templates"],
        }
        roots = get_template_roots(config)

        assert len(roots["project"]) == 1
        # Should be absolute
        assert roots["project"][0].is_absolute()
        # Should end with the relative path
        assert str(roots["project"][0]).endswith(".gai/templates")

    def test_relative_user_paths(self):
        """Test that relative user paths are resolved against home."""
        config = {
            "user-template-paths": [".config/gai/templates"],
        }
        roots = get_template_roots(config)

        assert len(roots["user"]) == 1
        # Should be absolute
        assert roots["user"][0].is_absolute()
        # Should start with home directory
        home_str = str(pathlib.Path.home())
        assert str(roots["user"][0]).startswith(home_str)

    def test_multiple_paths_per_tier(self):
        """Test multiple paths in a single tier."""
        config = {
            "project-template-paths": ["/tmp/project1", "/tmp/project2", "/tmp/project3"],
        }
        roots = get_template_roots(config)

        assert len(roots["project"]) == 3
        assert roots["project"][0] == pathlib.Path("/tmp/project1")
        assert roots["project"][1] == pathlib.Path("/tmp/project2")
        assert roots["project"][2] == pathlib.Path("/tmp/project3")

    def test_mixed_absolute_and_relative(self):
        """Test mixing absolute and relative paths."""
        config = {
            "project-template-paths": ["/tmp/absolute", "relative/path"],
        }
        roots = get_template_roots(config)

        assert len(roots["project"]) == 2
        assert roots["project"][0] == pathlib.Path("/tmp/absolute")
        # Second should be absolute after resolution
        assert roots["project"][1].is_absolute()

    def test_nonexistent_paths_included(self):
        """Test that nonexistent paths are still included in result."""
        config = {
            "project-template-paths": ["/tmp/nonexistent_path_12345"],
        }
        roots = get_template_roots(config)

        # Path should be in result even if it doesn't exist
        # Discovery function will skip it later
        assert len(roots["project"]) == 1
        assert roots["project"][0] == pathlib.Path("/tmp/nonexistent_path_12345")

    def test_single_string_converted_to_list(self):
        """Test that single string is handled (with warning)."""
        config = {
            "project-template-paths": "/tmp/single",  # Not a list
        }
        roots = get_template_roots(config)

        # Should still work, converting to list
        assert len(roots["project"]) == 1
        assert roots["project"][0] == pathlib.Path("/tmp/single")

    def test_all_tiers_together(self):
        """Test resolving all tiers at once."""
        config = {
            "project-template-paths": [".gai/templates"],
            "user-template-paths": ["~/.config/gai/templates"],
            "builtin-template-paths": ["/usr/share/gai/templates"],
        }
        roots = get_template_roots(config)

        assert len(roots["project"]) == 1
        assert len(roots["user"]) == 1
        assert len(roots["builtin"]) == 1
        # All should be absolute
        assert roots["project"][0].is_absolute()
        assert roots["user"][0].is_absolute()
        assert roots["builtin"][0].is_absolute()
