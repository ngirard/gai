"""Integration tests for CLI."""

import subprocess
import sys
import tempfile
from pathlib import Path


def test_cli_help():
    """Test that --help works."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage: gai" in result.stdout.lower()
    assert "available commands" in result.stdout.lower()


def test_cli_generate_config():
    """Test that --generate-config works."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "--generate-config"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "model" in result.stdout
    assert "temperature" in result.stdout


def test_cli_show_prompt():
    """Test that --show-prompt works with template variables."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Test document content")
        temp_path = f.name

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "gai",
                "--show-prompt",
                "--document",
                f"@:{temp_path}",
                "--input",
                "Test query",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Test document content" in result.stdout
        assert "Test query" in result.stdout
    finally:
        Path(temp_path).unlink()


def test_cli_invalid_temperature():
    """Test that invalid temperature raises proper error."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "--conf-temperature", "not-a-number", "--show-prompt"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Configuration error" in result.stderr or "error" in result.stderr.lower()


def test_cli_missing_template_value():
    """Test that missing template value raises proper error."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "--show-prompt", "--document"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Usage error" in result.stderr or "error" in result.stderr.lower()


def test_cli_nonexistent_file():
    """Test that nonexistent file reference raises proper error."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gai",
            "--show-prompt",
            "--document",
            "@:/nonexistent/file/path.txt",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "error" in result.stderr.lower()


def test_cli_unexpected_arg():
    """Test that unexpected argument raises proper error."""
    result = subprocess.run(
        [sys.executable, "-m", "gai", "unexpected"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Usage error" in result.stderr or "error" in result.stderr.lower()
