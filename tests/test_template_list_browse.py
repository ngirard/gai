"""Tests for template list and browse commands."""

import json
from unittest import mock

import pytest

from gai.cli import handle_template_browse, handle_template_list
from gai.config import DEFAULT_CONFIG
from gai.template_catalog import build_template_catalog


class TestBuildTemplateCatalog:
    """Tests for build_template_catalog function."""

    def test_build_catalog_empty(self):
        """Test building catalog with no configured paths."""
        config = DEFAULT_CONFIG.copy()
        catalog = build_template_catalog(config)
        assert len(catalog) == 0

    def test_build_catalog_with_templates(self, tmp_path):
        """Test building catalog with some templates."""
        # Create test templates
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "test.j2").write_text("{{ test }}")

        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "email.j2").write_text("{{ email }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]
        config["user-template-paths"] = [str(user_dir)]

        catalog = build_template_catalog(config)
        assert len(catalog) == 2
        logical_names = catalog.get_all_logical_names()
        assert "test" in logical_names
        assert "email" in logical_names


class TestHandleTemplateList:
    """Tests for handle_template_list function."""

    def test_list_empty_catalog(self, capsys):
        """Test listing with no templates."""
        config = DEFAULT_CONFIG.copy()
        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.format = "table"

        handle_template_list(config, parsed)

        captured = capsys.readouterr()
        assert "No templates found" in captured.out

    def test_list_table_format(self, tmp_path, capsys):
        """Test listing templates in table format."""
        # Create test templates
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "test.j2").write_text("{{ test }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]

        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.format = "table"

        handle_template_list(config, parsed)

        captured = capsys.readouterr()
        assert "TIER" in captured.out
        assert "LOGICAL NAME" in captured.out
        assert "RELATIVE PATH" in captured.out
        assert "project" in captured.out
        assert "test" in captured.out
        assert "test.j2" in captured.out

    def test_list_json_format(self, tmp_path, capsys):
        """Test listing templates in JSON format."""
        # Create test templates
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "test.j2").write_text("{{ test }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]

        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.format = "json"

        handle_template_list(config, parsed)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) == 1
        assert output[0]["logical_name"] == "test"
        assert output[0]["tier"] == "project"
        assert output[0]["relative_path"] == "test.j2"

    def test_list_filter_by_tier(self, tmp_path, capsys):
        """Test filtering templates by tier."""
        # Create test templates in multiple tiers
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "proj.j2").write_text("{{ proj }}")

        user_dir = tmp_path / "user"
        user_dir.mkdir()
        (user_dir / "user.j2").write_text("{{ user }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]
        config["user-template-paths"] = [str(user_dir)]

        parsed = mock.Mock()
        parsed.tier = "project"
        parsed.filter = None
        parsed.format = "table"

        handle_template_list(config, parsed)

        captured = capsys.readouterr()
        assert "proj" in captured.out
        assert "user" not in captured.out

    def test_list_filter_by_substring(self, tmp_path, capsys):
        """Test filtering templates by substring."""
        # Create test templates
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "email.j2").write_text("{{ email }}")
        (project_dir / "summary.j2").write_text("{{ summary }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]

        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = "email"
        parsed.format = "table"

        handle_template_list(config, parsed)

        captured = capsys.readouterr()
        assert "email" in captured.out
        assert "summary" not in captured.out


class TestHandleTemplateBrowse:
    """Tests for handle_template_browse function."""

    def test_browse_no_templates(self):
        """Test browse with no templates."""
        config = DEFAULT_CONFIG.copy()
        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.no_preview = False

        with pytest.raises(SystemExit) as exc_info:
            handle_template_browse(config, parsed)

        assert exc_info.value.code == 1

    @mock.patch("shutil.which")
    def test_browse_no_fzf(self, mock_which, tmp_path):
        """Test browse when fzf is not installed."""
        mock_which.return_value = None

        # Create a template
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "test.j2").write_text("{{ test }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]

        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.no_preview = False

        with pytest.raises(SystemExit) as exc_info:
            handle_template_browse(config, parsed)

        assert exc_info.value.code == 1

    @mock.patch("shutil.which")
    @mock.patch("subprocess.run")
    def test_browse_with_selection(self, mock_run, mock_which, tmp_path, capsys):
        """Test browse with a successful selection."""
        mock_which.return_value = "/usr/bin/fzf"

        # Create a template
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        test_file = project_dir / "test.j2"
        test_file.write_text("{{ test }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]

        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.no_preview = False

        # Mock fzf returning the selection
        expected_line = f"test\tproject\ttest.j2\t{test_file}"
        mock_run.return_value = mock.Mock(returncode=0, stdout=expected_line + "\n")

        handle_template_browse(config, parsed)

        captured = capsys.readouterr()
        assert captured.out.strip() == "test"

    @mock.patch("shutil.which")
    @mock.patch("subprocess.run")
    def test_browse_with_cancel(self, mock_run, mock_which, tmp_path):
        """Test browse when user cancels."""
        mock_which.return_value = "/usr/bin/fzf"

        # Create a template
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "test.j2").write_text("{{ test }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]

        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.no_preview = False

        # Mock fzf returning cancel (non-zero exit code)
        mock_run.return_value = mock.Mock(returncode=130, stdout="")

        with pytest.raises(SystemExit) as exc_info:
            handle_template_browse(config, parsed)

        assert exc_info.value.code == 1

    @mock.patch("shutil.which")
    @mock.patch("subprocess.run")
    def test_browse_with_no_preview(self, mock_run, mock_which, tmp_path, capsys):
        """Test browse with preview disabled."""
        mock_which.return_value = "/usr/bin/fzf"

        # Create a template
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        test_file = project_dir / "test.j2"
        test_file.write_text("{{ test }}")

        config = DEFAULT_CONFIG.copy()
        config["project-template-paths"] = [str(project_dir)]

        parsed = mock.Mock()
        parsed.tier = None
        parsed.filter = None
        parsed.no_preview = True

        # Mock fzf returning the selection
        expected_line = f"test\tproject\ttest.j2\t{test_file}"
        mock_run.return_value = mock.Mock(returncode=0, stdout=expected_line + "\n")

        handle_template_browse(config, parsed)

        captured = capsys.readouterr()
        assert captured.out.strip() == "test"

        # Verify that --preview was not in the fzf args
        call_args = mock_run.call_args
        fzf_args = call_args[0][0]
        assert "--preview" not in fzf_args
