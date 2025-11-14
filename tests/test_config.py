"""Tests for configuration module."""

import pytest

from gai.config import CONFIG_TYPES, _convert_config_values
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
