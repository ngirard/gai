"""Tests for new CLI subcommands."""

import subprocess
import sys
import tempfile
from pathlib import Path


def test_generate_command():
    """Test that 'generate' command works (would require API key)."""
    # We can't actually test generation without an API key,
    # but we can test that the command is recognized
    result = subprocess.run(
        [sys.executable, "-m", "gai", "generate", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "generate" in result.stdout.lower()


def test_generate_show_prompt():
    """Test 'generate --show-prompt' flag."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Test document")
        temp_path = f.name

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "gai",
                "generate",
                "--show-prompt",
                "--document",
                f"@:{temp_path}",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Test document" in result.stdout
    finally:
        Path(temp_path).unlink()


def test_config_view():
    """Test 'config view' command."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "config", "view"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Effective Configuration" in result.stdout
    assert "model" in result.stdout


def test_config_defaults():
    """Test 'config defaults' command."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "config", "defaults"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "model" in result.stdout
    assert "temperature" in result.stdout
    assert "gemini" in result.stdout.lower()


def test_config_path():
    """Test 'config path' command."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "config", "path"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "User configuration file path" in result.stdout
    assert ".config/gai/config.toml" in result.stdout
    assert "Repository configuration file path" in result.stdout
    assert ".gai/config.toml" in result.stdout


def test_config_validate_nonexistent():
    """Test 'config validate' with non-existent file."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gai",
            "config",
            "validate",
            "--file",
            "/tmp/nonexistent_config.toml",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stdout.lower()


def test_config_validate_valid():
    """Test 'config validate' with valid TOML file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".toml") as f:
        f.write('model = "gemini-flash-latest"\ntemperature = 0.5\n')
        temp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "gai", "config", "validate", "--file", temp_path],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "valid" in result.stdout.lower()
    finally:
        Path(temp_path).unlink()


def test_template_render():
    """Test 'template render' command."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gai",
            "template",
            "render",
            "--document",
            "Test content",
            "--input",
            "Test query",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Test content" in result.stdout
    assert "Test query" in result.stdout


def test_template_render_user_only():
    """Test 'template render --part user' command."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gai",
            "template",
            "render",
            "--part",
            "user",
            "--document",
            "User content",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "User content" in result.stdout
    # Should not include system instruction tags
    assert "<system_instruction>" not in result.stdout


def test_template_render_system_only():
    """Test 'template render --part system' command."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gai",
            "template",
            "render",
            "--part",
            "system",
            "--conf-system-instruction",
            "You are helpful",
            "--document",
            "Doc",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "You are helpful" in result.stdout
    # Should not include user instruction
    assert "<document>" not in result.stdout


def test_template_render_with_file():
    """Test 'template render' with file reference."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Content from file")
        temp_path = f.name

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "gai",
                "template",
                "render",
                "--document",
                f"@:{temp_path}",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Content from file" in result.stdout
    finally:
        Path(temp_path).unlink()


def test_backward_compatibility_help():
    """Test that old-style --help still works."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage: gai" in result.stdout.lower()
    assert "available commands" in result.stdout.lower()


def test_invocation_without_args_shows_help():
    """Running gai with no args should display help and exit cleanly."""

    result = subprocess.run(
        [sys.executable, "-m", "gai"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "usage: gai" in result.stdout.lower()
    assert "available commands" in result.stdout.lower()


def test_backward_compatibility_generate_config():
    """Test that old-style --generate-config still works."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "--generate-config"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "model" in result.stdout
    assert "temperature" in result.stdout


def test_backward_compatibility_show_prompt():
    """Test that old-style --show-prompt still works."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gai",
            "--show-prompt",
            "--document",
            "Test",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Test" in result.stdout


def test_config_help():
    """Test 'config --help' shows subcommands."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "config", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "view" in result.stdout
    assert "edit" in result.stdout
    assert "validate" in result.stdout
    assert "defaults" in result.stdout
    assert "path" in result.stdout


def test_template_help():
    """Test 'template --help' shows subcommands."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "template", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "render" in result.stdout


def test_template_render_help():
    """Test 'template render --help' shows options."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "template", "render", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--part" in result.stdout
    assert "user" in result.stdout
    assert "system" in result.stdout
