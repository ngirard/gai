"""Tests for configuration module."""

import pathlib
import tempfile

import pytest

from gai.config import (
    CONFIG_TYPES,
    _convert_config_values,
    _resolve_config_file_paths,
    load_config_from_file,
    load_effective_config,
    read_file_content,
)
from gai.exceptions import ConfigError


def test_convert_config_values_basic():
    """Test basic type conversion."""
    config_data = {
        "temperature": "0.5",
        "max-output-tokens": "100",
        "model": "gemini-2.0-flash-exp",
    }

    result = _convert_config_values(config_data, CONFIG_TYPES, "test")

    assert result["temperature"] == 0.5
    assert isinstance(result["temperature"], float)
    assert result["max-output-tokens"] == 100
    assert isinstance(result["max-output-tokens"], int)
    assert result["model"] == "gemini-2.0-flash-exp"


def test_convert_config_values_bool():
    """Test boolean conversion."""
    test_cases = [
        ({"enable-feature-x": "true"}, True),
        ({"enable-feature-x": "false"}, False),
        ({"enable-feature-x": "yes"}, True),
        ({"enable-feature-x": "no"}, False),
        ({"enable-feature-x": "1"}, True),
        ({"enable-feature-x": "0"}, False),
    ]

    for config_data, expected in test_cases:
        result = _convert_config_values(config_data, CONFIG_TYPES, "test")
        assert result["enable-feature-x"] == expected


def test_convert_config_values_none():
    """Test None value handling."""
    config_data = {
        "max-output-tokens": None,
    }

    result = _convert_config_values(config_data, CONFIG_TYPES, "test")
    assert result["max-output-tokens"] is None


def test_convert_config_values_invalid():
    """Test error handling for invalid values."""
    config_data = {
        "temperature": "not-a-number",
    }

    with pytest.raises(ConfigError):
        _convert_config_values(config_data, CONFIG_TYPES, "test")


def test_read_file_content_success():
    """Test reading file content successfully."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Test content")
        temp_path = f.name

    try:
        content = read_file_content(temp_path)
        assert content == "Test content"
    finally:
        pathlib.Path(temp_path).unlink()


def test_read_file_content_not_found():
    """Test reading non-existent file raises ConfigError."""
    with pytest.raises(ConfigError, match="File not found"):
        read_file_content("/nonexistent/file.txt")


def test_resolve_config_file_paths():
    """Test resolving @: paths in config."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Template from file")
        temp_path = f.name

    try:
        config = {
            "system-instruction": f"@:{temp_path}",
            "user-instruction": "Direct instruction",
            "model": "gemini-flash-latest",
        }

        resolved = _resolve_config_file_paths(config)

        assert resolved["system-instruction"] == "Template from file"
        assert resolved["user-instruction"] == "Direct instruction"
        assert resolved["model"] == "gemini-flash-latest"
    finally:
        pathlib.Path(temp_path).unlink()


def test_load_config_from_file_not_exists():
    """Test loading config from non-existent file returns empty dict."""
    # Use tempfile to create a path that doesn't exist (security S108)
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_path = pathlib.Path(tmpdir) / "nonexistent-config-file-12345.toml"
        config = load_config_from_file(fake_path)
        assert config == {}


def test_load_config_from_file_success():
    """Test loading valid TOML config file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".toml") as f:
        f.write('model = "gemini-2.0-flash-exp"\n')
        f.write("temperature = 0.5\n")
        temp_path = pathlib.Path(f.name)

    try:
        config = load_config_from_file(temp_path)
        assert config["model"] == "gemini-2.0-flash-exp"
        assert config["temperature"] == 0.5
    finally:
        temp_path.unlink()


def test_load_effective_config_defaults_only():
    """Test loading config with defaults only (no file, no CLI args)."""
    config = load_effective_config([])
    assert "model" in config
    assert "temperature" in config
    assert config["temperature"] == 0.1  # from DEFAULT_CONFIG


def test_load_effective_config_cli_override():
    """Test CLI arguments override defaults."""
    args = ["--conf-temperature", "0.9", "--conf-model", "gemini-pro"]
    config = load_effective_config(args)

    assert config["temperature"] == 0.9
    assert config["model"] == "gemini-pro"


def test_load_effective_config_missing_value():
    """Test missing value for --conf- argument raises error."""
    args = ["--conf-temperature"]

    with pytest.raises(ConfigError, match="requires a value"):
        load_effective_config(args)


def test_load_effective_config_empty_name():
    """Test empty config name after --conf- raises error."""
    args = ["--conf-", "value"]

    with pytest.raises(ConfigError, match="missing a name"):
        load_effective_config(args)
